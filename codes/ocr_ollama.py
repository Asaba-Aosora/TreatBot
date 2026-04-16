"""
医疗病历本地OCR处理 - 基于Ollama视觉模型
完全离线，零成本，支持GPU加速
"""
import requests
import base64
import json
import time
from pathlib import Path
from pdf2image import convert_from_path
from typing import Dict, Optional, List
from datetime import datetime

class OllamaOCR:
    """本地Ollama视觉OCR处理器"""
    
    def __init__(self, model: str = "llava:7b", ollama_url: str = "http://localhost:11434"):
        """
        初始化Ollama OCR
        
        Args:
            model: 模型名称
                - "llava:7b" 推荐（平衡速度和精度）
                - "llava:13b" 更强但更慢
                - "minicpm-v:latest" 很快但精度一般
            ollama_url: Ollama服务地址
        """
        self.model = model
        self.ollama_url = ollama_url
        self.api_endpoint = f"{ollama_url}/api/generate"
        
        # 检查Ollama服务
        self._check_ollama_service()
    
    def _check_ollama_service(self):
        """检查Ollama服务是否运行"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=2)
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [m['name'] for m in models]
                
                if self.model in model_names:
                    print(f"✅ Ollama服务正常，模型'{self.model}'已就绪")
                else:
                    print(f"⚠️  模型'{self.model}'未安装")
                    print(f"   已安装模型: {model_names}")
                    print(f"   请运行: ollama pull {self.model}")
            else:
                raise Exception("Ollama服务返回异常")
        except requests.ConnectionError:
            raise Exception(
                f"❌ 无法连接Ollama服务 ({self.ollama_url})\n"
                "   请确保已运行: ollama serve"
            )
    
    def image_to_base64(self, image_path: str) -> str:
        """将图片转为base64"""
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    
    def recognize_page(self, image_path: str, timeout: int = 120) -> Dict:
        """
        识别单页医疗病历
        
        Args:
            image_path: 图片路径
            timeout: 超时时间（秒），Ollama处理慢，需要足够的时间
        
        Returns:
            {
                'success': bool,
                'text': str,  # 识别的文本
                'model': str,
                'processing_time': float,
                'error': str  # 如果失败
            }
        """
        start_time = time.time()
        image_path = str(image_path)
        
        print(f"  🔍 识别: {Path(image_path).name}", end="", flush=True)
        
        # OCR提示词：只返回图像中的文本，不要解释或拒绝
        prompt = """You are an OCR engine. Extract only the visible text from this image.
Do not explain, do not summarize, and do not provide any medical advice or commentary.
Output only the raw text content found in the image.
If the image contains a table, preserve the row/column structure as plain text.
If text is not fully readable, return the best transcription.
Do not include any apologies, refusal statements, or policy text.
"""
        fallback_prompt = """You are an OCR engine. Extract only the visible text from this image.
Return the text content only, no explanations, no refusals, no judgments.
If the text is not clear, return the closest readable text.
"""
        
        def is_refusal_text(text: str) -> bool:
            lowered = text.lower()
            refusal_indicators = [
                '很抱歉', '无法帮助', '无法识别', '抱歉，我', 'not legible', 'unable to', 'cannot', 'sorry', 'cannot help'
            ]
            return any(keyword in lowered for keyword in refusal_indicators)
        
        def call_ollama(current_prompt: str):
            return requests.post(
                self.api_endpoint,
                json={
                    "model": self.model,
                    "prompt": current_prompt,
                    "images": [img_base64],
                    "stream": False,  # 等全部完成再返回
                    "temperature": 0.0,  # 最低温度，减少生成性回答
                },
                timeout=timeout
            )
        
        try:
            # 读取图片
            img_base64 = self.image_to_base64(image_path)
            
            # 调用Ollama API (使用vision模型)
            response = call_ollama(prompt)
            
            if response.status_code == 200:
                result = response.json()
                text = result.get('response', '').strip()

                if is_refusal_text(text):
                    print(" ⚠️ 识别结果像是拒绝回答，尝试简化提示词重试...", end="", flush=True)
                    response = call_ollama(fallback_prompt)
                    if response.status_code == 200:
                        result = response.json()
                        text = result.get('response', '').strip()

                elapsed = time.time() - start_time
                print(f" ✓ ({elapsed:.1f}s, {len(text)}字)")
                
                return {
                    'success': True,
                    'text': text,
                    'model': self.model,
                    'processing_time': elapsed
                }
            else:
                elapsed = time.time() - start_time
                error_msg = f"API错误: {response.status_code}"
                print(f" ❌ ({error_msg})")
                return {
                    'success': False,
                    'error': error_msg,
                    'processing_time': elapsed
                }
        
        except requests.Timeout:
            elapsed = time.time() - start_time
            print(f" ❌ (超时 {elapsed:.0f}s)")
            return {
                'success': False,
                'error': f'识别超时(>{timeout}s)',
                'processing_time': elapsed
            }
        except Exception as e:
            elapsed = time.time() - start_time
            print(f" ❌ ({str(e)[:30]})")
            return {
                'success': False,
                'error': str(e),
                'processing_time': elapsed
            }


class MedicalPDF:
    """医疗PDF处理器"""
    
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
    
    def convert_to_images(self, dpi: int = 400) -> List[object]:
        """
        将PDF转换为图片列表
        
        Args:
            dpi: 分辨率(150-200就够)
        
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
    
    def save_images(self, images: List[object], output_dir: str = "./temp_images") -> List[str]:
        """
        保存图片，返回路径列表
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        image_paths = []
        for i, image in enumerate(images):
            img_path = output_dir / f"page_{i+1}.png"
            image.save(img_path, "PNG")
            image_paths.append(str(img_path))
        
        return image_paths


class PatientExtractor:
    """患者信息提取器"""
    
    @staticmethod
    def extract_from_text(text: str, model_name: str = "llava:7b") -> Dict:
        """
        从识别的OCR文本中提取结构化患者信息
        
        使用正则表达式 + 模式匹配，不再依赖LLM（速度快）
        
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
                'allergies': List[str]
            }
        """
        import re
        
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
        
        # 诊断（通常在"诊断"或"主诊单"后）
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
        # 查找"一线"、"二线"、"三线"等关键词
        lines_pattern = r'(一线|二线|三线|四线|五线)'
        lines_matches = re.findall(lines_pattern, text)
        line_map = {'一线': 1, '二线': 2, '三线': 3, '四线': 4, '五线': 5}
        treatment_lines = [line_map[l] for l in lines_matches]
        result['treatment_lines'] = max(treatment_lines) if treatment_lines else None
        
        # 具体治疗方案（查找常见化疗药物名）
        chemo_drugs = ['紫杉醇', '顺铂', '吉西他滨', '氟尿嘧啶', '铂类', '化疗', '伊立替康', '贝伐', '赫赛汀', '卡培他滨']
        treatments = [drug for drug in chemo_drugs if drug in text]
        result['treatments'] = treatments if treatments else None
        
        # 过敏史
        allergy_pattern = r'(?:过敏史|过敏)\s*[:：]\s*([^\n]+)'
        allergy_match = re.search(allergy_pattern, text)
        result['allergies'] = allergy_match.group(1).split('、') if allergy_match else []
        
        return result


def process_pdf_with_ollama(
    pdf_path: str,
    model: str = "llava:7b",
    output_dir: str = "./output_patients",
    poppler_path: Optional[str] = None
) -> Dict:
    """
    完整的PDF→OCR→结构化提取流程（本地Ollama）
    
    Args:
        pdf_path: 输入PDF路径
        model: Ollama模型（推荐 "llava:7b"）
        output_dir: 输出目录
        poppler_path: Windows需要指定poppler路径
    
    Returns:
        {
            'success': bool,
            'patient': dict,  # 结构化患者信息
            'raw_texts': List[str],  # 每页的原始识别文本
            'processing_time': float,
            'pages': int
        }
    """
    
    start_time = time.time()
    print(f"\n{'='*60}")
    print(f"医疗病历OCR处理 (Ollama本地)")
    print(f"{'='*60}")
    
    try:
        # Step 1: PDF转图片
        pdf_processor = MedicalPDF(pdf_path, poppler_path)
        images = pdf_processor.convert_to_images(dpi=300)
        image_paths = pdf_processor.save_images(images, f"{output_dir}/temp_images")
        
        # Step 2: 初始化Ollama OCR
        ocr = OllamaOCR(model=model)
        
        # Step 3: 逐页识别
        print(f"\n🔍 开始识别 ({len(image_paths)} 页页面):")
        all_texts = []
        errors = []
        
        for i, img_path in enumerate(image_paths):
            result = ocr.recognize_page(img_path, timeout=120)
            
            if result['success']:
                all_texts.append(result['text'])
            else:
                errors.append(f"第{i+1}页: {result['error']}")
        
        if not all_texts:
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
        patient_info = PatientExtractor.extract_from_text(full_text, model)
        
        # Step 5: 保存结果
        output_path = Path(output_dir) / f"{Path(pdf_path).stem}_患者信息.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        result_data = {
            'success': True,
            'pdf_file': str(Path(pdf_path).name),
            'model': model,
            'patient': patient_info,
            'pages': len(all_texts),
            'raw_ocr_texts': all_texts,
            'errors': errors,
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
        print(f"📋 患者信息:")
        print(f"   - 姓名: {patient_info.get('name')}")
        print(f"   - 年龄: {patient_info.get('age')}")
        print(f"   - 性别: {patient_info.get('gender')}")
        print(f"   - 诊断: {patient_info.get('diagnosis')}")
        print(f"   - ECOG: {patient_info.get('ecog')}")
        print(f"   - 治疗线数: {patient_info.get('treatment_lines')}")
        print(f"{'='*60}\n")
        
        return result_data
    
    except Exception as e:
        print(f"\n❌ 处理失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e),
            'processing_time': time.time() - start_time
        }


if __name__ == "__main__":
    # 测试例子
    pdf_file = r"original_data/dataset_patient/基因检测报告/姓名：CHRO胆管癌 四川.pdf"
    
    # Windows用户，需要指定poppler路径
    poppler_path = r"D:\Asaba\Softwares\poppler-25.12.0\Library\bin"
    
    # 开始处理
    result = process_pdf_with_ollama(
        pdf_path=pdf_file,
        model="llava:7b",  # 改成你安装的模型 
        poppler_path=poppler_path
    )
    
    # 打印完整结果
    print("\n完整结果:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
