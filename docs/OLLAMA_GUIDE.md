# Ollama 医疗视觉模型选择指南

## 快速开始

### 1️⃣ 启动Ollama服务
```bash
ollama serve
# 保持此窗口开启（监听 localhost:11434）
```

### 2️⃣ 下载并安装模型（新开终端）

选择一个模型运行以下命令之一：

#### 🌟 推荐：LLaVA-7B（平衡方案）
```bash
ollama pull llava:7b
```
- ⚡ 速度：快（~30秒/页，8GB内存可用）
- 📊 精度：中等（80-90%，够用）
- 💾 显存：2-4GB
- ✅ 推荐原因：速度和精度平衡最好，显存占用低

---

#### 🔥 更强版本：LLaVA-13B
```bash
ollama pull llava:13b
```
- ⚡ 速度：较慢（~60秒/页）
- 📊 精度：高（90%+）
- 💾 显存：8-10GB
- ⚠️ 需要：显卡或足够的内存

---

#### ⚡ 最快版本：MiniCPM-V
```bash
ollama pull minicpm-v:latest
```
- ⚡ 速度：很快（~20秒/页）
- 📊 精度：一般（75-85%）
- 💾 显存：2GB
- ✅ 适合：老电脑或实时处理需求

---

#### 🇨🇳 中文最强：Yi-VL
```bash
ollama pull yi-vl:latest
```
- ⚡ 速度：慢（~90秒/页）
- 📊 精度：最强（95%+）
- 💾 显存：14-16GB
- ⚠️ 需要：高端显卡

---

## 性能对比表

| 模型 | 速度 | 中文识别 | 医学术语 | 表格识别 | 显存占用 | 推荐场景 |
|------|------|---------|---------|---------|---------|---------|
| **llava:7b** | ⭐⭐⭐⭐ | 🟡 | 🟡 | 🟡 | **低** | ✅ **通用最佳** |
| llava:13b | ⭐⭐⭐ | 🟢 | 🟢 | 🟢 | 中 | 需要高精度 |
| minicpm-v | ⭐⭐⭐⭐⭐ | 🟡 | 🟡 | 🟠 | **最低** | 老电脑/实时 |
| yi-vl | ⭐⭐ | 🟢 | 🟢 | 🟢 | 高 | 医学术语要求高 |

---

## 3️⃣ 配置模型并运行

编辑 `run_ocr.py` 中的 `MODEL` 变量：

```python
# 改这一行为你选择的模型
MODEL = "llava:7b"  # 或 "llava:13b" / "minicpm-v:latest" / "yi-vl:latest"
```

然后运行：
```bash
python run_ocr.py
```

---

## 🆘 常见问题

### Q1: 运行时报错 "无法连接Ollama服务"
**解决**: 
- 确保 `ollama serve` 正在运行（独立终端窗口）
- 检查地址是否为 `localhost:11434`

### Q2: 显存不足
**解决**:
- 改用 `minicpm-v:latest` （显存占用最低2GB）
- 或使用 CPU 运行：`OLLAMA_NUM_GPU=0 ollama serve`

### Q3: 识别很慢（超过2分钟/页）
**解决**:
- 改用 `minicpm-v:latest`（快10倍）
- 或启用GPU加速（需要NVIDIA显卡 + CUDA）

### Q4: 识别准确率低
**解决**:
- 改用 `llava:13b` 或 `yi-vl:latest`
- 提高PDF分辨率（在 ocr_ollama.py 改 `dpi=200` 或 `dpi=300`）

### Q5: 如何卸载模型节省空间?
```bash
ollama rm llava:7b
```

---

## 📊 显卡/CPU配置建议

### GPU 用户（NVIDIA）
```bash
# 自动优化，使用GPU加速
ollama serve
```

### CPU 用户
```bash
# 禁用GPU强制使用CPU
OLLAMA_NUM_GPU=0 ollama serve
```

### Mac 用户
```bash
# M1/M2/M3 自动使用Neural Engine
ollama serve
```

---

## 🎯 最佳实践

1. **首次使用**: 用 `llava:7b`（最平衡）
2. **医学要求严格**: 改 `yi-vl:latest` 或 `llava:13b`
3. **电脑很老**: 用 `minicpm-v:latest`
4. **显存不足**: 禁用GPU：`OLLAMA_NUM_GPU=0`

---

## 📝 成本对比

| 方案 | 方案成本 | 月成本（处理1000份病历） |
|------|---------|------------------------|
| **本地Ollama** | ❌ 零成本 | **¥0** |
| 硅基流动API | 按token计费 | ¥100-200 |
| Claude API | 按token计费 | ¥200-500 |

**总结**: 用本地Ollama，一次性下载模型，永久免费使用！

---

## 快速命令参考

```bash
# 查看已安装模型
ollama list

# 启动服务
ollama serve

# 下载模型
ollama pull llava:7b
ollama pull minicpm-v:latest
ollama pull yi-vl:latest

# 删除模型
ollama rm llava:7b

# 在线测试模型（可选）
ollama run llava:7b "识别这个URL的图片: https://..."
```

---

**建议**: 选择 `llava:7b` 开始，根据效果再决定是否升级到其他模型。
