# 化验指标规范 ID 与同义词（用于归一化与试验文本解析）
# metric_id 使用稳定英文 slug，便于后续入库与国际化

METRIC_ALIASES: dict[str, list[str]] = {
    "wbc": ["白细胞", "wbc", "white blood cell", "白血球"],
    "anc": ["中性粒细胞", "anc", "neutrophil", "中性粒细胞绝对值"],
    "plt": ["血小板计数", "血小板", "plt", "platelet"],
    "hb": ["血红蛋白", "hb", "hemoglobin", "hgb", "血红蛋白浓度"],
    "tbil": ["总胆红素", "tbil", "bilirubin", "血清总胆红素"],
    "alt": ["alt", "谷丙转氨酶", "丙氨酸氨基转移酶"],
    "ast": ["ast", "谷草转氨酶", "天门冬氨酸氨基转移酶"],
    "cr": ["肌酐", "creatinine", "cr", "血肌酐", "scr"],
    "alb": ["白蛋白", "alb", "albumin"],
    "inr": ["inr", "国际标准化比值", "凝血酶原时间国际标准化比值"],
    "aptt": ["aptt", "活化部分凝血活酶时间"],
    "pt": ["pt", "凝血酶原时间"],
}

GENOMICS_HINTS = ("突变", "基因", "exon", "错义", "tmb", "kras", "tp53", "融合", "扩增", "拷贝数")

NARRATIVE_HINTS = (
    "入院", "出院", "主诉", "查体", "医嘱", "病史", "体格检查", "临床诊断",
    "院号", "姓名", "性别", "籍贯", "送检材料", "报告版本",
)
