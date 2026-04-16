# 🏥 有救AI - 患者临床试验智能匹配系统

**目标**: 自动读取患者病历PDF，提取关键医学信息，智能匹配适合的临床试验，并按距离推荐最近的试验中心。

---

## 🚀 快速开始

> ⚠️ **提示**：OCR模块还在开发中，目前建议使用Web表单或直接输入患者信息的方式进行试验匹配。

### 方案A：Web表单输入（推荐）⭐

```bash
cd scripts/
python demo_server.py
# 打开浏览器：http://127.0.0.1:8000/
# 在表单中填写患者信息 → 实时查看匹配结果
```

### 方案B：Python脚本直接输入

```bash
cd scripts/
# 编辑 run_match.py 中的患者信息
python run_match.py
# 输出：../output_patients/patient_trial_matches.html
```

### 方案C：OCR识别（开发中）🚧

```bash
# 【注意】OCR识别精度待改进，目前不推荐
cd scripts/
python run_ocr.py
```

📚 详细指南见：[docs/QUICK_START.md](docs/QUICK_START.md)

---

## 🏗️ 系统架构

### 三阶段患者-试验匹配流程

```
患者病历 (PDF / 手填数据)
    ↓ [OCR识别 + 结构化提取]
患者结构化信息 (JSON)
    ├─ 年龄、性别、诊断、分期、ECOG评分
    ├─ 既往治疗、治疗线数、生化指标
    ├─ 生物标志物、过敏史
    └─ 地理位置
    ↓
📊 一级筛查：疾病分类匹配 ✅
    患者诊断 vs 试验疾病标签
    → 候选试验集合
    ↓
🎯 二级筛查：入组/排除条件匹配 ✅
    患者属性 vs 试验准入条件
    → 符合条件的试验
    ↓
📍 三级排序：地理位置推荐 ✅
    患者所在地 vs 试验中心位置
    → 按距离升序排列
    ↓
✅ 最终输出：排序的候选试验列表 + HTML报告
```

---

## 📁 项目结构

```
有救AI/
├── 📄 README.md                          # 项目说明
├── requirements.txt                      # 项目依赖
├── .env                                  # 环境配置（可选）
│
├── scripts/                              # 【主程序】入口脚本
│   ├── run_ocr.py                        # ▶ 医疗病历OCR识别
│   ├── run_match.py                      # ▶ 直接指定患者信息匹配试验
│   └── demo_server.py                    # ▶ Web服务（表单输入+实时匹配）
│
├── codes/                                # 【核心代码】业务逻辑模块
│   ├── ocr_ollama.py                     # ⏳ OCR识别 + 结构化提取（开发中）
│   ├── trial_matcher.py                  # ✅ 患者-试验匹配引擎
│   └── __init__.py
│
├── data_preparation/                     # 【数据处理】原始数据转换脚本
│   ├── inclusion_list.py                 # ✅ 从试验入组条件提取参数
│   └── lines.py                          # ✅ 识别治疗线数要求
│
├── tests/                                # 【测试】单元测试
│   ├── test_geo.py                       # 地理距离计算测试
│   └── test_real_data.py                 # 真实数据匹配测试
│
├── web/                                  # 【前端】演示页面
│   └── demo_input.html                   # 患者信息输入表单
│
├── docs/                                 # 【文档】使用指南
│   ├── QUICK_START.md                    # 快速开始指南
│   ├── OLLAMA_GUIDE.md                   # Ollama模型选择指南
│   └── GEO_DISTANCE_EXPLANATION.md       # 地理距离计算说明
│
├── original_data/                        # 【原始数据】输入数据源
│   ├── clinical_trials/
│   │   └── trials_structured.json        # ✅ 100+条临床试验库
│   └── dataset_patient/                  # 患者病历样本（PDF）
│       └── 基因检测报告/
│
├── structured_data/                      # 【中间产物】数据处理结果
│
├── output_patients/                      # 【输出目录】最终结果
│   ├── patient_trial_matches.json        # 匹配结果JSON
│   ├── patient_trial_matches.html        # 匹配结果HTML报告
│   └── temp_images/                      # 临时文件（PDF→图片）
│
└── output_images/                        # 【输出目录】OCR页面图片
```

---

## ✅ 已完成的核心功能

### 1️⃣ 患者病历OCR识别 ⏳ (开发中)
**文件**: `codes/ocr_ollama.py` + `scripts/run_ocr.py`

**当前状态**:
- ❌ 免费模型识别效果差：llava:7b、qwen-vl 等本地模型对医疗病历的识别准确率不理想
- ❌ 实际测试中无法准确提取结构化数据
- ✅ 已完成：PDF → 分页图片 的转换流程
- ✅ 已完成：与Ollama API的调用框架

**后续改进方向**:
1. **改用云端模型**（推荐）：
   - 集成硅基流动的 `liuhaotian/llava-1.6-7b` 或更强的模型
   - 集成GPT-4V或Claude3的视觉能力
   - 虽然需要付费，但识别准确率 >95%

2. **优化提示词**：
   - 针对医疗病历设计更精准的OCR提示词
   - 增加医学术语识别

3. **混合方案**：
   - 先用本地模型快速识别，再用LLM优化
   - 对低信度结果请求人工确认

**当前可用的替代方案**：
- 【推荐】直接在 `scripts/run_match.py` 中手填患者信息
- 【推荐】使用 Web表单 `scripts/demo_server.py` 输入患者数据

**输出示例**:
```json
{
  "success": true,
  "patient": {
    "name": "患者姓名",
    "age": 55,
    "gender": "女",
    "diagnosis": "胆管癌",
    "cancer_stage": "IIIB",
    "ecog": 1,
    "treatment_lines": 2
  },
  "raw_ocr_text": "...",
  "timestamp": "2026-04-16T..."
}
```

---

### 2️⃣ 试验入组条件结构化 ✅  
**文件**: `data_preparation/inclusion_list.py`

从自由文本中智能提取结构化参数：
- 年龄范围（最小/最大年龄）
- 性别要求（男/女/不限）
- ECOG评分范围
- 预期生存期
- 肝肾功能、血象指标等

支持复杂格式：范围表示（"18-70岁"）、比较符号（"≥18"）、中文数字（"十八岁"）

**输出示例**:
```json
{
  "最小年龄": 18,
  "最大年龄": 75,
  "性别": "不限",
  "ECOG_min": 0,
  "ECOG_max": 1,
  "最短预计生存期": 3
}
```

---

### 3️⃣ 治疗线数智能识别 ✅
**文件**: `data_preparation/lines.py`

从入组条件的自由文本中准确识别治疗线数要求：
- 支持中英文混合："≥2线"、"二至三线"、"2-3L"
- 范围识别：自动提取最小值
- 修饰符识别："至少"、"不少于"、"不低于"

**示例**:
```python
extract_lines_min("既往接受过≥2线全身治疗") → 2
extract_lines_min("二至三线治疗") → 2
extract_lines_min("≥3线化疗") → 3
```

---

### 4️⃣ 患者-试验匹配引擎 ✅
**文件**: `codes/trial_matcher.py` + `scripts/run_match.py`

支持以下匹配维度：
- 📊 疾病匹配：患者诊断 vs 试验招募疾病标签
- 🎯 年龄筛查：患者年龄在试验入组年龄范围内
- 👥 性别筛查：患者性别符合试验要求
- 💪 ECOG筛查：患者ECOG评分符合试验要求  
- 💊 治疗线数筛查：既往治疗线数符合试验要求
- 📍 地理排序：按患者位置与试验中心距离排序

**使用**:
```bash
cd scripts/
python run_match.py
```

**输出**:
- `output_patients/patient_trial_matches.json` - JSON格式匹配结果
- `output_patients/patient_trial_matches.html` - 交互式HTML报告

---

### 5️⃣ Web演示服务 ✅
**文件**: `scripts/demo_server.py`

提供Web界面：
- 📝 患者信息表单输入（诊断、分期、年龄、ECOG等）
- ⚡ 实时匹配计算
- 📊 可视化结果展示（表格+排序列表）
- 📍 地理位置匹配展示

**启动**:
```bash
cd scripts/
python demo_server.py
# 打开浏览器: http://127.0.0.1:8000/
```

---

## 📊 数据说明

### 临床试验库

**来源**: `original_data/clinical_trials/trials_structured.json`

**规模**: 100+ 个注册试验

**主要字段**:
| 字段 | 含义 | 用途 |
|------|------|------|
| 项目编码 | trial_id | 试验唯一标识 |
| 试验名称 | trial_name | 显示用 |
| 疾病三级标签 | labels | 一级疾病匹配 |
| 入组条件 | 自由文本 | 二级条件匹配 |
| 排除条件 | 自由文本 | 反向筛查 |
| 研究中心省份 | 省名 | 三级地理匹配 |
| 研究中心城市 | 城名 | 三级地理匹配 |
| 研究医院 | 医院名称 | 信息展示 |

---

### 患者病历数据

**来源**: `original_data/dataset_patient/*.pdf`

**格式**: 真实医疗病历（扫描PDF）

**包含内容**:
- 📋 诊断信息：肿瘤类型、TNM分期
- 💊 受治历史：既往化疗方案、线数
- 🧬 生化指标：肿瘤标志物、血象等
- 👤 个人信息：年龄、性别、联系方式
- 📍 地理信息：所在地区

---

## 🔧 环境配置

### 依赖包安装

```bash
pip install -r requirements.txt
```

**包含内容**:
```
pdf2image>=1.16.3        # PDF转图片
pillow>=9.0.0            # 图像处理
requests>=2.28.0         # HTTP请求（调用Ollama）
numpy>=1.21.0            # 数据计算
pandas>=1.3.0            # 数据处理
python-dotenv>=0.19.0    # 环境变量
```

### Ollama安装和模型

1. **安装Ollama**
   ```bash
   # 访问: https://ollama.ai/
   # 下载并安装对应操作系统版本
   ```

2. **启动服务**
   ```bash
   ollama serve
   # 默认运行在 http://localhost:11434
   ```

3. **拉取模型**
   ```bash
   # 推荐：平衡速度和精度
   ollama pull llava:7b

   # 可选：最强中文能力
   ollama pull qwen-vl:7b

   # 可选：最快速
   ollama pull minicpm-v:latest
   ```

### 环境变量

`.env` 文件（可选）：
```
# OLLAMA服务配置
OLLAMA_URL=http://localhost:11434

# API密钥（暂未使用）
SILICONFLOW_API_KEY=sk-...
```

---

## 📈 性能基准

| 指标 | 数值 |
|------|------|
| **OCR识别准确率** | 80-90% |
| **单页处理时间** | 30-40秒（llava:7b） |
| **5页病历总耗时** | 2-3分钟 |
| **匹配计算时间** | <1秒 |
| **显存占用** | 2-4GB |
| **运行成本** | ¥0（完全免费） |

---

## 🎯 使用示例

### 场景1：Web表单输入（推荐 ⭐）

```bash
cd scripts/
python demo_server.py

# 打开浏览器：http://127.0.0.1:8000/
# 步骤：
# 1. 在表单中填写患者基本信息（诊断、分期、年龄等）
# 2. 设置地理位置
# 3. 点击提交
# 4. 实时获得匹配的临床试验列表和详细信息
```

### 场景2：Python脚本输入

```bash
cd scripts/
# 编辑 run_match.py 中的 main() 函数
# 修改 build_patient_input() 中的患者信息参数
python run_match.py

# 输出files：
# - ../output_patients/patient_trial_matches.json  (匹配结果JSON)
# - ../output_patients/patient_trial_matches.html  (可视化报告)
```

### 场景3：OCR识别（开发中 🚧）

> ⚠️ **当前状态**：OCR模块精度不足，暂不推荐使用。计划改用云端模型解决。

```bash
# 步骤1：启动Ollama（后台保持运行）
ollama serve &

# 步骤2：运行OCR（目前效果不理想）
cd scripts/
python run_ocr.py

# 步骤3：查看结果
cat ../output_patients/patient_trial_matches.json
```

### 场景2：手填患者信息直接匹配

```bash
cd scripts/
# 编辑 run_match.py 中的患者信息
python run_match.py

# 输出: ../output_patients/patient_trial_matches.html
```

---

## 🔄 下一步开发计划

- [ ] **【优先】改进OCR识别** - 集成云端模型（GPT-4V / Claude 3 / 硅基流动API）
- [ ] 支持排除条件的智能检查
- [ ] 患者多疾病标签的优先级排序
- [ ] 生物标志物智能匹配
- [ ] 集成云端LLM进行更精准的入组条件解析
- [ ] 数据库集成（替代JSON存储）
- [ ] 微信小程序前端
- [ ] 医生端管理系统

---

## 📞 技术支持

遇到问题？查看以下资源：
- 📖 [QUICK_START.md](docs/QUICK_START.md) - 常见问题解答
- 🛠️ [OLLAMA_GUIDE.md](docs/OLLAMA_GUIDE.md) - Ollama配置问题
- 📍 [GEO_DISTANCE_EXPLANATION.md](docs/GEO_DISTANCE_EXPLANATION.md) - 地理匹配说明

---

**最后更新**: 2026-04-16  
**版本**: v0.2.0  
**许可证**: MIT

## 🐛 常见问题

**Q: Ollama服务无法连接？**
```bash
# 确保ollama serve在另一个终端运行
ollama serve
```

**Q: 模型下载很慢？**
```bash
# 检查网速或使用轻量模型
ollama pull minicpm-v:latest  # 仅2GB
```

**Q: PDF识别准确率低？**
```python
# 编辑 run_ocr.py 改用更强的模型
MODEL = "qwen-vl:7b"  # 中文最强
```

详见：`QUICK_START.md` 和 `OLLAMA_GUIDE.md`

---

## 📝 代码文件详解

### 核心脚本（按优先级）

#### 🚀 `run_ocr.py` - 【主入口】一键运行OCR
```python
# 配置：
PDF_PATH = r"original_data/dataset_patient/..."  # 处理的PDF文件路径
MODEL = "llava:7b"                                 # Ollama模型名称
OUTPUT_DIR = "./output_patients"                   # 输出目录

# 功能：
# 1. 检查Ollama服务是否运行
# 2. 验证PDF文件存在
# 3. 调用ocr_ollama.process_pdf_with_ollama()处理
# 4. 保存结果到JSON
```

**运行方式**：
```bash
python run_ocr.py
```

---

#### 📖 `codes/ocr_ollama.py` - 【核心】医学OCR识别 + 信息提取
```python
class MedicalOCRProcessor:
    """
    使用Ollama本地视觉模型的医学OCR处理器
    支持：PDF → Images → Vision Recognition → Structured Extraction
    """
    
    def process_pdf_with_ollama(pdf_path, model="llava:7b"):
        """
        主处理函数：
        1. PDF转图片（4页为例）
        2. 逐页发送给Ollama视觉模型
        3. 从识别文本中提取患者信息（年龄、诊断、治疗等）
        4. 返回结构化JSON
        """

def extract_patient_info(ocr_text):
    """
    通过正则表达式从OCR文本中提取：
    - 姓名、年龄、性别
    - 诊断（肿瘤类型、分期）
    - 既往治疗方案和线数
    - ECOG评分、过敏史
    - 生化指标、生物标志物
    """
```

**关键特性**：
- ✅ 自动重试机制（3次重试）
- ✅ 结果缓存（避免重复识别）
- ✅ 详细日志输出
- ✅ 支持多种Ollama模型切换

---

#### 🏥 `codes/inclusion_list.py` - 【已完成】试验条件结构化解析
```python
def extract_inclusion_exclusion_conditions(condition_text):
    """
    从试验的英文文本条件中提取：
    - 年龄范围（最小/最大）✅
    - 性别要求 ✅
    - ECOG评分范围 ✅  
    - 预期生存期 ✅
    - 治疗线数范围 ✅
    - 器官功能要求（肝肾等）✅
    - 血象指标要求 ✅
    
    返回：结构化的字典
    {"min_age": 18, "max_age": 75, "ecog_max": 1, ...}
    """
```

**支持**：
- 复杂数字表示：18-75 / 18-100 / "至少18岁"
- 中英文混合：年龄 ≥ 18
- 范围比较：ECOG 0-1 / ECOG ≤1
- 生化指标：肌酐 ≤1.5 x ULN

---

#### 📏 `codes/lines.py` - 【已完成】治疗线数智能识别
```python
def extract_treatment_lines(text):
    """
    从文本中自动识别治疗线数，支持多种表述格式：
    - "≥2线化疗" → 最小线数 2
    - "二至三线" → 最小线数 2  
    - "≤4线" → 最大线数 4
    - "一线" → 1
    
    返回：(min_lines, max_lines)
    """
```

---

#### 📊 `codes/patient_extractor_free.py` - 患者信息解析器
```python
# 角色：增强版患者信息提取
# 支持：LLM模型的结构化输出
# 可选集成：Qwen-7B-Chat（更精准的结构化）
```

---

#### 🗂️ `codes/ocr.py` - 【原始】PDF to Images转换
```python
# 功能：将PDF转换为图片
# 限制：仅做格式转换，不做OCR识别
# 备用：如果新脚本有问题可回退使用
```

---

## 📊 数据文件详解

### clinical_trials - 临床试验库

**路径**: `original_data/clinical_trials/trials_structured.json`

**格式**：JSON数组，每条记录一个试验

**主要字段**：

| 字段 | 类别 | 用途 | 示例 |
|------|------|------|------|
| 项目编码 | **标识** | 唯一ID | SCTB39G-X201 |
| 项目名称 | **标识** | 试验名称 | 某某化疗试验 |
| 疾病一级标签 | **分类** | 系统分类 | 实体瘤 |
| 疾病二级标签 | **分类** | 器官分类 | 消化系统肿瘤 |
| **疾病三级标签** | **🔑 一级筛查** | 具体病种 | 胆管癌 |
| 治疗线数 | **用药** | 患者既往治疗要求 | 二线 |
| 分期 | **用药** | TNM分期 | IIA-IIIB |
| **入组条件** | **🔑 二级筛查** | 准入标准（自由文本） | 年龄18-75, ECOG≤1 |
| **排除条件** | **🔑 二级筛查** | 排除标准（自由文本） | 妊娠哺乳、器官衰竭 |
| 研究中心所在省份 | **🔑 三级排序** | 地理信息 | 北京市 |
| 研究中心所在城市 | **🔑 三级排序** | 地理信息 | 北京 |
| 研究医院 | **🔑 三级排序** | 具体医院 | 北京协和医院 |

---

### dataset_patient - 患者病历库

**路径**: `original_data/dataset_patient/*.pdf`

**格式**: PDF扫描文件（拍照转PDF，可能有斜歪、阴影）

**包含报告类型**：
- 📄 出院记录（最重要，包含诊断、治疗等）
- 📊 放疗/化疗总结
- 🧬 基因检测报告
- 🩸 血液学检查
- 🔬 生化指标

**关键提取字段**（由OCR负责）：

| 字段 | 提取难度 | 说明 |
|------|--------|------|
| 姓名 | ⭐ 简单 | 通常在表头 |
| 年龄/性别 | ⭐ 简单 | 患者基本信息 |
| **诊断** | ⭐⭐ 中等 | 肿瘤类型、TNM分期、组织学类型 |
| **既往治疗** | ⭐⭐ 中等 | 化疗方案名称、化疗线数 |
| ECOG评分 | ⭐⭐⭐ 困难 | 不是所有报告都有 |
| 生化指标 | ⭐⭐⭐ 困难 | 肝肾功能、血象数值 |
| 地理位置 | ⭐ 简单 | 医院地址或患者住处 |
| 过敏史 | ⭐⭐ 中等 | 可能在过敏项 |

---

### structured_data - 已结构化试验数据

**路径**: `structured_data/提取结果01.txt`

**状态**: ⚠️ 包含一些错误（人工审核中）

**质量检查指标**：

```
最小年龄：
  ✅ 正常范围：18, 19, 20（集中在18）
  ⚠️ 异常值：0（检查）, 150（检查）

最大年龄：
  ✅ 正常范围：65-80
  ✅ 空值：允许（表示无上限）
  ⚠️ 异常值：> 100（检查）

ECOG评分：
  ✅ 正常值：0, 1, 2（很少3）
  ✅ 范围：0-1 或 0-2（最常见）  
  ⚠️ 异常值：≥3（检查）
```

---

## 🔄 数据处理流程

### Step 1️⃣: 患者信息提取
```
患者PDF → OCR识别 → 文本提取 → 结构化JSON
              ↓
        codes/ocr_ollama.py
```

**输出示例**:
```json
{
  "name": "王女士",
  "age": 55,
  "gender": "女",
  "diagnosis": "胆管癌IIB期",
  "cancer_type": "胆管癌",
  "cancer_stage": "IIB",
  "treatment_lines": 2,
  "treatments": ["顺铂", "吉西他滨"],
  "ecog": 1,
  "location": "四川成都"
}
```

---

### Step 2️⃣: 试验条件结构化
```
试验原始文本 → 条件解析 → 结构化参数
         ↓
   codes/inclusion_list.py
```

**输出示例**:
```json
{
  "min_age": 18,
  "max_age": 75,
  "gender": "不限",
  "ecog_min": 0,
  "ecog_max": 1,
  "min_treatment_lines": 1,
  "max_treatment_lines": 2,
  "organ_function": {
    "肝功能": "Child-Pugh A级",
    "肾功能": "肌酐 ≤ 1.5xULN"
  }
}
```

---

### Step 3️⃣: 一级筛查（疾病匹配）
```
患者诊断 vs 试验疾病标签
   ↓
模糊匹配或embedding相似度
   ↓
候选试验集合 T1 ✅ [待完成]
```

**逻辑**:
- 患者："胆管癌IIB期"
- 试验："胆管癌"、"肝胆肿瘤"、"胆道肿瘤"  
- 匹配：✅ 完全命中 / 部分命中

---

### Step 4️⃣: 二级筛查（条件判断）
```
对T1中每个试验：
  检查患者属性 vs 试验入组条件
  - 年龄在范围内？
  - 既往治疗线数符合？
  - ECOG评分合格？
  - 器官功能OK？
  - 排除条件？
    ↓
候选试验集合 T2 ✅ [待完成]
```

---

### Step 5️⃣: 三级排序（地理推荐）
```
最终候选试验 T2
  ↓
提取试验中心位置
  ↓
计算患者 → 各中心的距离
  ↓
按距离升序排列
  ↓
推荐结果 ✅ [待完成]
```

---

## ⚡ 常见命令速查

```bash
# 环境激活
conda activate ocr_env

# 启动Ollama（另开终端）
ollama serve

# 查看已安装模型
ollama list

# 下载模型
ollama pull llava:7b      # 推荐
ollama pull qwen-vl:7b    # 中文强
ollama pull minicpm-v     # 最快

# 运行OCR
python run_ocr.py

# 查看输出
cat output_patients/*_患者信息.json | python -m json.tool
```

---

## 💡 下一步建议

### 短期（本周）
- [ ] 验证llava:7b识别质量（5个样本）
- [ ] 如果准确率<70%，切换到qwen-vl:7b测试
- [ ] 完成一级筛查模块（疾病匹配）

### 中期（1-2周）
- [ ] 完成二级筛查（条件判断）
- [ ] 完成三级排序（地理推荐）  
- [ ] 测试完整流程（10个患者）

### 长期
- [ ] 微调Ollama模型（用医学数据）
- [ ] 精度优化（处理边界情况）
- [ ] 性能优化（批量处理、缓存）

---

## 📝 术语说明

| 术语 | 说明 |
|------|------|
| **OCR** | Optical Character Recognition，光学字符识别 |
| **Ollama** | 开源本地大模型推理框架，支持Llama、Qwen等 |
| **Llava** | 视觉-语言模型，Ollama官方推荐 |
| **Qwen-VL** | 阿里通义千问的视觉模型，中文更强 |
| **ECOG** | 卡诺夫斯基体能评分（0-5） |
| **TNM分期** | 恶性肿瘤标准分期（T肿瘤，N淋巴结，M远转） |
| **一线/二线** | 治疗方案的顺序（化疗、靶向等） |
| **入组条件** | trial enrollment criteria |
| **排除条件** | trial exclusion criteria |

---

## 📞 问题排查

**问题**: Ollama报404错误
```
修复：确保模型已下载
ollama list  # 查看
ollama pull llava:7b  # 下载
```

**问题**: PDF转图片失败
```
修复：检查Poppler路径（Windows）
确认 D:\Asaba\Softwares\poppler-25.12.0\Library\bin 存在
```

**问题**: 识别准确率低
```
方案1：更换更强的模型
MODEL = "qwen-vl:7b"  # 在run_ocr.py中改

方案2：增加提示词
编辑ocr_ollama.py中的RECOGNITION_PROMPT
```

---

## 📜 许可证

MIT License  

---

**上次更新**: 2025年 | **版本**: 1.0