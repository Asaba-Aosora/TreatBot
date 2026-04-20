"""
医疗病历OCR处理 - 基于多模态LLM API
支持kimi、豆包、阿里云OCR等云端服务
准确性高，特别适合医学检验报告的数值区间识别
"""
import base64
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import requests
from dotenv import load_dotenv
from pdf2image import convert_from_path
from openai import OpenAI

from codes.lab_normalize import attach_lab_observations

# 加载环境变量
load_dotenv()

class CloudOCR:
    """云端多模态LLM OCR处理器"""

    def __init__(self, provider: str = "doubao", api_key: Optional[str] = None):
        """
        初始化云端OCR

        Args:
            provider: 服务提供商
                - "doubao": 豆包 (推荐，医学检验报告最准)
                - "kimi": Kimi
                - "aliyun": 阿里云OCR
            api_key: API密钥，如果不提供则从环境变量读取
        """
        self.provider = provider.lower()

        # API密钥配置
        if api_key:
            self.api_key = api_key
        else:
            key_map = {"doubao": "ARK_API_KEY", "kimi": "KIMI_API_KEY", "aliyun": "ALIYUN_API_KEY"}
            if self.provider == "doubao":
                # 兼容历史变量名
                self.api_key = os.getenv("ARK_API_KEY") or os.getenv("DOUBAO_API_KEY")
            else:
                env_key = key_map.get(self.provider)
                self.api_key = os.getenv(env_key)

        if not self.api_key:
            raise ValueError(
                f"请设置 {key_map.get(self.provider)} 环境变量或直接传入api_key"
            )

        # 配置各服务的基础信息
        self._setup_provider_config()

    def _setup_provider_config(self):
        """配置各服务提供商的参数"""
        configs = {
            "doubao": {
                "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                "model": os.getenv("DOUBAO_MODEL", "doubao-seed-1-6-vision-250815"),
                "headers": {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
            },
            "kimi": {
                "base_url": "https://api.moonshot.cn/v1",
                "model": "moonshot-v1-8k-vision-preview",
                "headers": {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
            },
            "aliyun": {
                "base_url": "https://ocr-api.cn-hangzhou.aliyuncs.com",
                "appcode": self.api_key,  # 阿里云使用AppCode
                "headers": {
                    "Authorization": f"APPCODE {self.api_key}",
                    "Content-Type": "application/json"
                }
            }
        }

        if self.provider not in configs:
            raise ValueError(f"不支持的服务提供商: {self.provider}")

        self.config = configs[self.provider]
        print(f"✅ {self.provider.upper()} OCR服务已配置")

    def image_to_base64(self, image_path: Union[str, Path]) -> str:
        """将图片转为base64"""
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')

    def recognize_page_doubao(self, image_path: str, timeout: int = 60, fast_mode: bool = False) -> Dict:
        """
        使用豆包API识别单页
        """
        img_base64 = self.image_to_base64(image_path)

        prompt = """你是一个专业的医疗OCR识别引擎。请准确识别图片中的所有文本内容。

要求：
1. 完整提取所有可见文本，不要遗漏
2. 保持表格的行列结构，用制表符或清晰格式表示
3. 数值区间（如参考值范围）必须准确识别
4. 不要添加任何解释、评论或额外内容
5. 直接返回识别的文本内容

如果图片中包含表格，请用以下格式表示：
项目名称    结果    参考范围    单位
血常规    正常    -    -
白细胞    6.5    4.0-10.0    10^9/L

直接返回文本，不要任何多余内容。"""
        if fast_mode:
            prompt = """请快速识别图片中的医疗文字并直接输出纯文本：
1. 优先保证主文本可读，不需要严格表格重建
2. 保留行顺序
3. 不要解释和补充"""

        try:
            client = OpenAI(
                base_url=self.config["base_url"],
                api_key=self.api_key,
            )
            start_time = time.time()
            response = client.responses.create(
                model=self.config["model"],
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_image", "image_url": f"data:image/png;base64,{img_base64}"},
                            {"type": "input_text", "text": prompt},
                        ],
                    }
                ],
                timeout=timeout,
            )
            elapsed = time.time() - start_time
            text = getattr(response, "output_text", "") or ""
            if not text and hasattr(response, "output"):
                # 兼容部分SDK返回结构
                chunks = []
                for item in response.output:
                    content = getattr(item, "content", []) or []
                    for part in content:
                        if getattr(part, "type", "") in ("output_text", "text"):
                            chunks.append(getattr(part, "text", ""))
                text = "\n".join(chunks).strip()

            if not text:
                return {
                    "success": False,
                    "error": "豆包返回为空，请检查模型权限或输入格式",
                    "processing_time": elapsed,
                }
            return {
                "success": True,
                "text": text.strip(),
                "model": self.config["model"],
                "processing_time": elapsed,
            }
        except Exception as e:
            if "timeout" in str(e).lower():
                return {
                    'success': False,
                    'error': f'请求超时(>{timeout}s)',
                    'processing_time': timeout
                }
            return {
                'success': False,
                'error': str(e),
                'processing_time': 0
            }

    def recognize_page_kimi(self, image_path: str, timeout: int = 60) -> Dict:
        """
        使用Kimi API识别单页
        """
        img_base64 = self.image_to_base64(image_path)

        prompt = """请准确识别图片中的所有医疗文本内容。

要求：
1. 完整提取所有可见文本
2. 保持表格结构和数值区间
3. 直接返回识别内容，不要解释
4. 特别注意医学检验数值和参考范围的准确性"""

        payload = {
            "model": self.config["model"],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_base64}"
                            }
                        }
                    ]
                }
            ],
            "temperature": 0.1,
            "max_tokens": 4096
        }

        try:
            response = requests.post(
                f"{self.config['base_url']}/chat/completions",
                headers=self.config["headers"],
                json=payload,
                timeout=timeout
            )

            if response.status_code == 200:
                result = response.json()
                text = result["choices"][0]["message"]["content"].strip()

                return {
                    'success': True,
                    'text': text,
                    'model': self.config["model"],
                    'processing_time': response.elapsed.total_seconds()
                }
            else:
                return {
                    'success': False,
                    'error': f"API错误: {response.status_code} - {response.text}",
                    'processing_time': response.elapsed.total_seconds()
                }

        except requests.Timeout:
            return {
                'success': False,
                'error': f'请求超时(>{timeout}s)',
                'processing_time': timeout
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'processing_time': 0
            }

    def recognize_page_aliyun(self, image_path: str, timeout: int = 30) -> Dict:
        """
        使用阿里云OCR API识别单页
        """
        img_base64 = self.image_to_base64(image_path)

        # 阿里云通用文字识别
        payload = {
            "image": img_base64,
            "configure": {
                "format": "JSON"
            }
        }

        try:
            response = requests.post(
                f"{self.config['base_url']}/api/predict/ocr_general",
                headers=self.config["headers"],
                json=payload,
                timeout=timeout
            )

            if response.status_code == 200:
                result = response.json()

                if result.get("success"):
                    # 提取识别结果
                    text_lines = []
                    for item in result.get("prism_wordsInfo", []):
                        text_lines.append(item.get("word", ""))

                    text = "\n".join(text_lines)

                    return {
                        'success': True,
                        'text': text,
                        'model': 'aliyun_ocr_general',
                        'processing_time': response.elapsed.total_seconds()
                    }
                else:
                    return {
                        'success': False,
                        'error': result.get("msg", "阿里云OCR识别失败"),
                        'processing_time': response.elapsed.total_seconds()
                    }
            else:
                return {
                    'success': False,
                    'error': f"API错误: {response.status_code} - {response.text}",
                    'processing_time': response.elapsed.total_seconds()
                }

        except requests.Timeout:
            return {
                'success': False,
                'error': f'请求超时(>{timeout}s)',
                'processing_time': timeout
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'processing_time': 0
            }

    def _recognize_once(self, image_path: str, timeout: int = 60, fast_mode: bool = False) -> Dict:
        if self.provider == "doubao":
            return self.recognize_page_doubao(image_path, timeout, fast_mode=fast_mode)
        if self.provider == "kimi":
            return self.recognize_page_kimi(image_path, timeout)
        if self.provider == "aliyun":
            return self.recognize_page_aliyun(image_path, timeout)
        return {
            "success": False,
            "error": f"不支持的服务提供商: {self.provider}",
            "processing_time": 0,
        }

    def recognize_page(
        self,
        image_path: str,
        timeout: int = 60,
        max_retries: int = 2,
        fast_mode: bool = False,
        quiet: bool = False,
    ) -> Dict:
        """
        识别单页医疗病历

        Args:
            image_path: 图片路径
            timeout: 超时时间（秒）

        Returns:
            {
                'success': bool,
                'text': str,  # 识别的文本
                'model': str,
                'processing_time': float,
                'error': str  # 如果失败
            }
        """
        if not quiet:
            print(f"  🔍 识别: {Path(image_path).name}", end="", flush=True)

        result = None
        for attempt in range(max_retries + 1):
            result = self._recognize_once(image_path, timeout, fast_mode=fast_mode)
            if result["success"]:
                break
            if attempt < max_retries:
                backoff = 2 ** attempt
                if not quiet:
                    print(f" 重试{attempt + 1}/{max_retries}...", end="", flush=True)
                time.sleep(backoff)

        if not quiet:
            if result['success']:
                print(f" ✓ ({result['processing_time']:.1f}s, {len(result['text'])}字)")
            else:
                print(f" ❌ ({result['error']})")

        return result


class MedicalPDF:
    """医疗PDF处理器（复用之前的实现）"""

    def __init__(self, pdf_path: str, poppler_path: Optional[str] = None):
        """
        初始化PDF处理

        Args:
            pdf_path: PDF文件路径
            poppler_path: Poppler安装路径(Windows需要指定)
        """
        self.pdf_path = Path(pdf_path)
        self.poppler_path = poppler_path

        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF不存在: {pdf_path}")

    def convert_to_images(self, dpi: int = 300) -> List[object]:
        """
        将PDF转换为图片列表

        Args:
            dpi: 分辨率(推荐300-400)

        Returns:
            PIL Image对象列表
        """
        print(f"📄 转换PDF: {self.pdf_path.name}")

        try:
            images = convert_from_path(
                str(self.pdf_path),
                dpi=dpi,
                poppler_path=self.poppler_path
            )
            print(f"✓ 成功转换为 {len(images)} 页")
            return images
        except Exception as e:
            raise RuntimeError(f"PDF转换失败: {e}")

    def save_images(
        self,
        images: List[object],
        output_dir: str = "./temp_images",
        fast_mode: bool = False,
    ) -> List[str]:
        """
        保存图片，返回路径列表
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        image_paths = []
        for i, image in enumerate(images):
            if fast_mode:
                img_path = output_dir / f"page_{i+1}.jpg"
                image.save(img_path, "JPEG", quality=68, optimize=True)
            else:
                img_path = output_dir / f"page_{i+1}.png"
                image.save(img_path, "PNG")
            image_paths.append(str(img_path))

        return image_paths


class PatientExtractor:
    """患者信息提取器（复用之前的实现，增强数值识别）"""

    @staticmethod
    def extract_from_text(text: str, model_name: str = "doubao") -> Dict:
        """
        从识别的OCR文本中提取结构化患者信息

        增强版：特别处理医学检验数值和区间

        Returns:
            {
                'name': str,
                'age': int,
                'gender': str,
                'diagnosis': str,
                'cancer_stage': str,
                'treatment_lines': int,
                'treatments': List[str],
                'ecog': int,
                'allergies': List[str],
                'lab_results': List[Dict]  # 新增：检验结果
            }
        """
        result = {}

        # 年龄
        age_pattern = r'(?:年龄|患者年龄|Age)\s*[:：]\s*(\d+)'
        age_match = re.search(age_pattern, text)
        result['age'] = int(age_match.group(1)) if age_match else None

        # 性别
        gender_pattern = r'(?:性别|患者性别|Gender)\s*[:：]\s*(男|女|Male|Female|M|F)'
        gender_match = re.search(gender_pattern, text)
        if gender_match:
            g = gender_match.group(1)
            result['gender'] = '男' if g in ['男', 'Male', 'M'] else '女'
        else:
            result['gender'] = None

        # 姓名
        name_pattern = r'(?:患者姓名|姓名|Name)\s*[:：]\s*(\S+?)(?:\s|,|$|[，。])'
        name_match = re.search(name_pattern, text)
        result['name'] = name_match.group(1) if name_match else None

        # 诊断
        diagnosis_pattern = r'(?:主诊断|诊断|Diagnosis)\s*[:：]\s*([^\n]+)'
        diagnosis_match = re.search(diagnosis_pattern, text)
        result['diagnosis'] = diagnosis_match.group(1).strip() if diagnosis_match else None

        # TNM分期
        stage_pattern = r'(?:TNM|T期|分期).*?([TtNnMm][\dab])[\dab]*.*?(?:[^A-Za-z0-9]|$)'
        stage_matches = re.findall(stage_pattern, text)
        result['cancer_stage'] = ''.join(stage_matches).upper() if stage_matches else None

        # ECOG评分
        ecog_pattern = r'ECOG\s*[:：]?\s*(\d)'
        ecog_match = re.search(ecog_pattern, text)
        result['ecog'] = int(ecog_match.group(1)) if ecog_match else None

        # 化疗方案 / 治疗线数
        lines_pattern = r'(一线|二线|三线|四线|五线)'
        lines_matches = re.findall(lines_pattern, text)
        line_map = {'一线': 1, '二线': 2, '三线': 3, '四线': 4, '五线': 5}
        treatment_lines = [line_map[l] for l in lines_matches]
        result['treatment_lines'] = max(treatment_lines) if treatment_lines else None

        # 具体治疗方案
        chemo_drugs = ['紫杉醇', '顺铂', '吉西他滨', '氟尿嘧啶', '铂类', '化疗', '伊立替康', '贝伐', '赫赛汀', '卡培他滨']
        treatments = [drug for drug in chemo_drugs if drug in text]
        result['treatments'] = treatments if treatments else None

        # 过敏史
        allergy_pattern = r'(?:过敏史|过敏)\s*[:：]\s*([^\n]+)'
        allergy_match = re.search(allergy_pattern, text)
        result['allergies'] = allergy_match.group(1).split('、') if allergy_match else []

        # 检验结果：仅在疑似「检验/实验室」相关段落抽取，减少出院小结、医嘱等噪声
        lab_segments = []
        for segment in re.split(r"---页面分割---", text):
            if re.search(
                r"检验|实验室|化验|血常规|血象|血细胞|生化全套|生化|凝血|肝肾功|肝功|肾功|"
                r"电解质|肿瘤标志物|指标汇总|参考范围|参考值",
                segment,
                re.I,
            ):
                lab_segments.append(segment)
        if lab_segments:
            result["lab_results"] = PatientExtractor.extract_lab_results("\n".join(lab_segments))
        else:
            result["lab_results"] = PatientExtractor.extract_lab_results(
                "", allow_fallback=True, fallback_source=text
            )

        return result

    @staticmethod
    def extract_lab_results(
        text: str,
        allow_fallback: bool = False,
        fallback_source: Optional[str] = None,
    ) -> List[Dict]:
        """
        提取医学检验结果，特别处理数值区间

        Returns:
            [
                {
                    'item': str,  # 检验项目
                    'value': str,  # 结果值
                    'unit': str,   # 单位
                    'range': str,  # 参考范围
                    'status': str  # 状态（正常/异常等）
                }
            ]
        """
        results: List[Dict] = []

        def _reject_narrative(item: str, unit: str, ref_range: Optional[str]) -> bool:
            bad_item = (
                "出院医嘱",
                "入院",
                "主诉",
                "现病史",
                "查体",
                "体格检查",
                "病程记录",
                "嘱患者",
                "回家",
                "复查",
                "注意事项",
                "医嘱",
                "谈话记录",
                "诊断依据",
                "出院带药",
            )
            if any(x in item for x in bad_item):
                return True
            if any(x in unit for x in ("天", "周", "月", "复查", "口服", "按时", "嘱", "回家")):
                return True
            cn_item = sum(1 for ch in item if "\u4e00" <= ch <= "\u9fff")
            if cn_item > 22:
                return True
            if len(item) > 28:
                return True
            if unit and len(unit) > 14:
                if not re.search(
                    r"g/l|/l|10\^|×10|^%$|u/l|iu/l|mmol|μmol|umol|阴性|阳性|mg/l|pg/ml|miu|fs/l|fl$",
                    unit,
                    re.I,
                ):
                    return True
            if re.search(r"\d\s*-\s*\d", item) and ("天" in item or "周" in item):
                return True
            return False

        pattern = r"^(.+?)\s+([\d.]+)\s*([^\d\s]+)?\s*([\d.-]+(?:\s*[-~]\s*[\d.]+)?)?"
        lines = text.split("\n") if text else []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            match = re.match(pattern, line)

            if match:
                item, value, unit, ref_range = match.groups()

                item = item.strip()

                if len(item) < 2 or any(
                    skip in item.lower() for skip in ["日期", "时间", "医院", "医生", "检验者"]
                ):
                    continue
                if _reject_narrative(item, unit or "", ref_range):
                    continue

                result = {
                    "item": item,
                    "value": value,
                    "unit": unit or "",
                    "range": ref_range or "",
                    "status": "",
                }

                # 判断状态
                if ref_range:
                    try:
                        # 解析参考范围
                        if '-' in ref_range:
                            low, high = ref_range.split('-')
                            low = float(low.strip())
                            high = float(high.strip())
                            val = float(value)

                            if val < low:
                                result['status'] = '偏低'
                            elif val > high:
                                result['status'] = '偏高'
                            else:
                                result['status'] = '正常'
                        elif '~' in ref_range:
                            low, high = ref_range.split('~')
                            low = float(low.strip())
                            high = float(high.strip())
                            val = float(value)

                            if val < low:
                                result['status'] = '偏低'
                            elif val > high:
                                result['status'] = '偏高'
                            else:
                                result['status'] = '正常'
                    except (ValueError, TypeError):
                        result['status'] = '无法判断'

                results.append(result)

        if not results and allow_fallback and fallback_source:
            # 无明确检验段落时：仅在全文中含制表符的短行上回退，减少叙事误匹配
            short = fallback_source[:12000]
            for line in short.split("\n"):
                line = line.strip()
                if not line or "\t" not in line:
                    continue
                m = re.match(pattern, line)
                if not m:
                    continue
                item, value, unit, ref_range = m.groups()
                item = item.strip()
                if _reject_narrative(item, unit or "", ref_range):
                    continue
                if len(item) > 24:
                    continue
                results.append(
                    {
                        "item": item,
                        "value": value,
                        "unit": unit or "",
                        "range": ref_range or "",
                        "status": "",
                    }
                )

        return results

    @staticmethod
    def validate_patient_info(patient: Dict) -> List[Dict]:
        issues = []
        required_fields = ["age", "gender", "diagnosis"]
        for field in required_fields:
            if not patient.get(field):
                issues.append(
                    {"severity": "high", "code": f"missing_{field}", "message": f"关键字段缺失: {field}"}
                )

        age = patient.get("age")
        if isinstance(age, int) and (age < 0 or age > 120):
            issues.append({"severity": "high", "code": "invalid_age", "message": f"年龄超出合理范围: {age}"})

        ecog = patient.get("ecog")
        if isinstance(ecog, int) and (ecog < 0 or ecog > 5):
            issues.append({"severity": "medium", "code": "invalid_ecog", "message": f"ECOG超出合理范围: {ecog}"})

        if patient.get("lab_results") and len(patient["lab_results"]) < 3:
            issues.append({"severity": "low", "code": "few_lab_items", "message": "检验项目较少，建议人工复核"})
        return issues


def classify_ocr_error(error_msg: str) -> Dict:
    msg = (error_msg or "").lower()
    if "timeout" in msg or "超时" in msg:
        return {"severity": "medium", "code": "timeout", "message": error_msg}
    if "429" in msg or "rate" in msg or "限流" in msg:
        return {"severity": "medium", "code": "rate_limit", "message": error_msg}
    if "401" in msg or "403" in msg or "apikey" in msg:
        return {"severity": "high", "code": "auth_error", "message": error_msg}
    return {"severity": "low", "code": "ocr_page_failed", "message": error_msg}


def _select_key_pages_for_hq(texts: List[str], top_k: int = 2) -> List[int]:
    """根据FAST识别结果挑选需要高精度复扫的页索引。"""
    keywords = [
        "检验", "化验", "血常规", "生化", "病理", "诊断", "免疫",
        "肿瘤", "ecog", "tnm", "治疗", "方案",
    ]
    scored = []
    for idx, text in enumerate(texts):
        lower = (text or "").lower()
        score = sum(lower.count(k) for k in keywords)
        if len(lower) < 80:
            score += 2
        scored.append((score, idx))
    scored.sort(key=lambda x: (x[0], -x[1]), reverse=True)
    chosen = [i for _, i in scored[: min(top_k, len(scored))]]
    return sorted(set(chosen))


def _ocr_pages_parallel(
    image_paths: List[str],
    ocr: CloudOCR,
    timeout: int,
    max_retries: int,
    fast_mode: bool,
    workers: int,
) -> Tuple[List[str], List[str], List[Dict]]:
    """并发逐页 OCR，保持页序。返回 (texts_per_page, errors, issues)。"""
    n = len(image_paths)
    texts: List[str] = [""] * n
    errors: List[str] = []
    issues: List[Dict] = []

    def run_one(idx_path: Tuple[int, str]) -> Tuple[int, Dict]:
        idx, path = idx_path
        return idx, ocr.recognize_page(
            path, timeout=timeout, max_retries=max_retries, fast_mode=fast_mode, quiet=True
        )

    workers = max(1, min(workers, n))
    if workers == 1:
        for i, path in enumerate(image_paths):
            r = ocr.recognize_page(
                path, timeout=timeout, max_retries=max_retries, fast_mode=fast_mode, quiet=False
            )
            if r["success"]:
                texts[i] = r["text"]
            else:
                errors.append(f"第{i+1}页: {r['error']}")
                issues.append({**classify_ocr_error(r["error"]), "page": i + 1})
        return texts, errors, issues

    print(f"  ⚡ 并发识别 workers={workers}")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_one, (i, p)) for i, p in enumerate(image_paths)]
        for fut in as_completed(futures):
            i, r = fut.result()
            if r["success"]:
                texts[i] = r["text"]
            else:
                errors.append(f"第{i+1}页: {r['error']}")
                issues.append({**classify_ocr_error(r["error"]), "page": i + 1})
    return texts, errors, issues


def process_pdf_with_cloud_ocr(
    pdf_path: str,
    provider: str = "doubao",
    api_key: Optional[str] = None,
    output_dir: str = "./output_patients",
    poppler_path: Optional[str] = None,
    fast_mode: bool = False,
    max_pages: Optional[int] = None,
    run_mode: str = "hybrid",
    ocr_max_pages: Optional[int] = None,
    page_concurrency: int = 4,
    hybrid_hq_top_k: Optional[int] = None,
) -> Dict:
    """
    完整的PDF→OCR→结构化提取流程（云端多模态LLM）

    Args:
        pdf_path: 输入PDF路径
        provider: 服务提供商 ("doubao", "kimi", "aliyun")
        api_key: API密钥
        output_dir: 输出目录
        poppler_path: Windows需要指定poppler路径
        fast_mode: 快速模式（降分辨率、短prompt、低重试）
        max_pages: 最大处理页数（None表示全部，仅 FAST 模式历史兼容）
        run_mode: 运行模式（hybrid/fast/quality）
        ocr_max_pages: 所有模式下最多 OCR 的页数（控制总耗时，None 读环境变量 OCR_MAX_PAGES）
        page_concurrency: 并发识别页数（建议 2~6，受 API 限流影响）
        hybrid_hq_top_k: 混合模式高精度复扫页数（默认读 HYBRID_HQ_TOP_K 或 2）

    Returns:
        {
            'success': bool,
            'patient': dict,  # 结构化患者信息
            'lab_results': List[Dict],  # 检验结果
            'raw_texts': List[str],  # 每页的原始识别文本
            'processing_time': float,
            'pages': int,
            'provider': str
        }
    """

    start_time = time.time()
    print(f"\n{'='*60}")
    print(f"医疗病历OCR处理 (云端{provider.upper()})")
    print(f"{'='*60}")

    try:
        # 兼容旧参数：如果显式传了fast_mode，则优先fast
        if fast_mode:
            run_mode = "fast"
        if run_mode not in ("hybrid", "fast", "quality"):
            run_mode = "hybrid"

        env_max = os.getenv("OCR_MAX_PAGES", "").strip()
        effective_max = ocr_max_pages
        if effective_max is None and env_max.isdigit():
            effective_max = int(env_max)
        if run_mode == "fast" and max_pages and max_pages > 0:
            effective_max = max_pages

        workers = max(1, min(page_concurrency, 12))

        env_hq = os.getenv("HYBRID_HQ_TOP_K", "").strip()
        hq_k = hybrid_hq_top_k if hybrid_hq_top_k is not None else (int(env_hq) if env_hq.isdigit() else 2)

        # Step 1: PDF转图片
        pdf_processor = MedicalPDF(pdf_path, poppler_path)
        use_fast = run_mode in ("hybrid", "fast")
        dpi = 160 if use_fast else 300
        images = pdf_processor.convert_to_images(dpi=dpi)
        if effective_max and effective_max > 0:
            images = images[:effective_max]
            print(f"⚡ 仅 OCR 前 {len(images)} 页 (ocr_max_pages={effective_max})")
        image_paths = pdf_processor.save_images(
            images,
            f"{output_dir}/temp_images",
            fast_mode=use_fast,
        )

        # Step 2: 初始化云端OCR
        ocr = CloudOCR(provider=provider, api_key=api_key)

        # Step 3: 逐页识别（可并发）
        print(f"\n🔍 开始识别 ({len(image_paths)} 页页面):")
        timeout = 32 if use_fast else 60
        retries = 0 if use_fast else 2
        all_texts, errors, issues = _ocr_pages_parallel(
            image_paths, ocr, timeout, retries, use_fast, workers
        )

        # 混合模式：先FAST扫全页，再对关键页做高精度复扫
        if run_mode == "hybrid" and all_texts:
            key_pages = _select_key_pages_for_hq(all_texts, top_k=max(1, hq_k))
            print(f"\n🔁 HYBRID模式: 对关键页做高精度复扫 -> {', '.join(str(i + 1) for i in key_pages)}")
            for page_idx in key_pages:
                hq_path = Path(output_dir) / "temp_images" / f"page_{page_idx + 1}_hq.png"
                images[page_idx].save(hq_path, "PNG")
                hq_result = ocr.recognize_page(
                    str(hq_path),
                    timeout=60,
                    max_retries=1,
                    fast_mode=False,
                )
                if hq_result["success"]:
                    all_texts[page_idx] = hq_result["text"]

        if not any((t or "").strip() for t in all_texts):
            print("\n❌ 所有页面识别失败")
            return {
                'success': False,
                'error': '无法识别任何页面',
                'errors': errors,
                'processing_time': time.time() - start_time
            }

        # Step 4: 合并文本并提取患者信息
        print(f"\n💾 提取患者信息...")
        full_text = "\n\n---页面分割---\n\n".join(all_texts)
        patient_info = PatientExtractor.extract_from_text(full_text, provider)
        attach_lab_observations(patient_info)
        issues.extend(PatientExtractor.validate_patient_info(patient_info))

        # Step 5: 保存结果
        output_path = Path(output_dir) / f"{Path(pdf_path).stem}_患者信息.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        result_data = {
            'success': True,
            'pdf_file': str(Path(pdf_path).name),
            'provider': provider,
            'mode': run_mode,
            'fast_mode': run_mode == "fast",
            'ocr_max_pages': effective_max,
            'page_concurrency': workers,
            'hybrid_hq_top_k': hq_k if run_mode == "hybrid" else None,
            'patient': patient_info,
            'pages': len(all_texts),
            'raw_ocr_texts': all_texts,
            'errors': errors,
            'issues': issues,
            'processing_time': time.time() - start_time,
            'timestamp': datetime.now().isoformat()
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)

        # 打印总结
        elapsed = time.time() - start_time
        print(f"\n✅ 处理完成!")
        print(f"{'='*60}")
        print(f"⏱️  总耗时: {elapsed:.1f}秒")
        print(f"📁 结果: {output_path}")

        if patient_info.get('lab_results'):
            print(f"🔬 检验结果: {len(patient_info['lab_results'])} 项")

        return result_data

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n❌ 处理失败: {e}")
        return {
            'success': False,
            'error': str(e),
            'processing_time': elapsed
        }


# 使用示例
if __name__ == "__main__":
    # 示例：使用豆包处理PDF
    result = process_pdf_with_cloud_ocr(
        pdf_path="path/to/medical_report.pdf",
        provider="doubao",  # 或 "kimi", "aliyun"
        output_dir="./output_patients"
    )

    if result['success']:
        print("患者信息:", result['patient'])
        print("检验结果:", result['patient'].get('lab_results', []))