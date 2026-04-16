# 🚀 快速上手指南 - Ollama本地OCR方案

## 三步快速开始（5分钟）

### Step 1️⃣  安装Ollama（2分钟）

```bash
# Windows/Mac: 访问 https://ollama.ai/ 下载安装
# Linux: curl -fsSL https://ollama.ai/install.sh | sh

# 安装完后，在终端验证
ollama --version
```

---

### Step 2️⃣  下载模型（3分钟）

```bash
# 启动Ollama服务（保持运行）
ollama serve

# 新开一个终端，拉取模型
ollama pull llava:7b
# 首次下载约4GB，需要2-5分钟（取决于网速）
```

**等待下载完成，你会看到**：
```
100% ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ 4.1 GB
```

---

### Step 3️⃣  运行OCR处理（1分钟）

```bash
# 在项目根目录运行
python run_ocr.py
```

**你会看到这样的输出**：
```
============================================================
          医疗病历OCR处理 (Ollama本地)
============================================================

📄 转换PDF: 姓名：CHRO胆管癌 四川.pdf
✓ 成功转换为 5 页

🔍 开始识别 (5 页页面):
  🔍 识别: page_1.png ✓ (35.2s, 1250字)
  🔍 识别: page_2.png ✓ (32.8s, 1180字)
  ...

✅ 处理完成!
============================================================
⏱️  总耗时: 180.5秒
📁 结果: ./output_patients/姓名：CHRO胆管癌 四川_患者信息.json
📋 患者信息:
   - 姓名: XXXX
   - 年龄: 55
   - 性别: 女
   - 诊断: 胆管癌
   - ECOG: 1
   - 治疗线数: 2
============================================================
```

---

## 📊 性能预期

| 项目 | 预期值 |
|------|--------|
| 首次运行 | 需要联网下载模型（4GB，3-10分钟） |
| 后续处理 | 每页30-40秒（llava:7b） |
| 5页病历 | 约2-3分钟 |
| 识别准确率 | 中等（80-90%，够用） |
| 成本 | **零成本**（本地处理） |

---

## 🔧 如果出错

### 错误1️⃣ : "无法连接Ollama服务"

```bash
# 确保ollama serve在运行
# 在一个独立的终端运行
ollama serve

# 然后在另一个终端运行 python run_ocr.py
```

### 错误2️⃣ : "模型llava:7b未安装"

```bash
# 拉取模型
ollama pull llava:7b

# 验证安装
ollama list
# 应该看到 llava:7b 列出
```

### 错误3️⃣ : "显存不足" 或 "内存不足"

```bash
# 改用轻量级模型
# 编辑 run_ocr.py，改这一行：
MODEL = "minicpm-v:latest"  # 只需2GB内存

# 重新下载
ollama pull minicpm-v:latest
```

### 错误4️⃣ : "PDF路径不对"

```python
# 编辑 run_ocr.py，改这一行
PDF_PATH = r"你的PDF文件路径"

# 例如：
PDF_PATH = r"original_data/dataset_patient/你的病历.pdf"
```

---

## 📁 输出文件位置

所有结果保存在 `./output_patients/` 目录：

```
output_patients/
├── temp_images/            # 临时图片文件
│   ├── page_1.png
│   ├── page_2.png
│   └── ...
└── 姓名：CHRO胆管癌 四川_患者信息.json  # ⭐ 最终结果
```

**JSON文件内容**：
```json
{
  "success": true,
  "pdf_file": "姓名：CHRO胆管癌 四川.pdf",
  "model": "llava:7b",
  "patient": {
    "name": "CHRO",
    "age": 55,
    "gender": "女",
    "diagnosis": "胆管癌",
    "cancer_stage": "IIIB",
    "ecog": 1,
    "treatment_lines": 2,
    "treatments": ["顺铂", "吉西他滨"],
    "allergies": []
  },
  "pages": 5,
  "processing_time": 180.5
}
```

---

## 🌟 提示

1. **初次运行慢？** 这是正常的，LLM第一次需要加载到显存/内存
2. **识别不准？** 改用更强的模型（见 OLLAMA_GUIDE.md）
3. **想要离线用？** 模型下载后就可以永久离线使用
4. **想加速处理？** 用 GPU 运行（需要NVIDIA显卡 + CUDA）

---

## 🎯 下一步

OCR完成后，你可以：

1. **查看提取结果** → `./output_patients/*.json`
2. **手动验证** → 检查是否有遗漏的关键信息
3. **进行试验匹配** → 用患者信息去匹配临床试验（下一阶段）

---

**有问题？** 查看完整文档：`OLLAMA_GUIDE.md`

**代码问题？** 检查：`codes/ocr_ollama.py` 中的错误提示
