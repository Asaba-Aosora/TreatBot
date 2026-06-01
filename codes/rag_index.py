"""
改进的向量索引实现：支持真实 embedding + Faiss 检索

之前的哈希方案已弃用，改为使用 SentenceTransformer 进行真实的语义向量化。
"""

import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class CriterionChunk:
    """试验条款 chunk"""
    chunk_id: str
    trial_id: str
    chunk_type: str  # 'inclusion' 或 'exclusion'
    text: str
    vector: List[float]
    metadata: Dict


class TrialVectorIndex:
    """向量索引（使用 SentenceTransformer + Faiss）"""
    
    def __init__(self, dim: int = 384, use_faiss: bool = True):
        """
        初始化向量索引
        
        Args:
            dim: 向量维度（SentenceTransformer 默认 384）
            use_faiss: 是否使用 Faiss（推荐 True）
        """
        self.dim = dim
        self.use_faiss = use_faiss
        self.chunks: List[CriterionChunk] = []
        self.faiss_index = None
        self.embeddings_array = None
        
        if use_faiss:
            try:
                import faiss
                self.faiss = faiss
            except ImportError:
                raise ImportError("请先安装 faiss: pip install faiss-cpu")
    
    def add_chunk(self, chunk_id: str, trial_id: str, chunk_type: str, 
                  text: str, vector: List[float], metadata: Dict):
        """添加一个 chunk"""
        self.chunks.append(
            CriterionChunk(
                chunk_id=chunk_id,
                trial_id=trial_id,
                chunk_type=chunk_type,
                text=text,
                vector=vector,
                metadata=metadata,
            )
        )
    
    def build_faiss_index(self):
        """构建 Faiss 索引（在所有 chunks 添加后调用）"""
        if not self.use_faiss or not self.chunks:
            return
        
        import numpy as np
        
        # 收集所有向量
        vectors = np.array([chunk.vector for chunk in self.chunks], dtype='float32')
        
        # 创建 IndexFlatL2（L2 距离）
        self.faiss_index = self.faiss.IndexFlatL2(vectors.shape[1])
        self.faiss_index.add(vectors)
        self.embeddings_array = vectors
        
        print(f"✅ Faiss 索引已构建: {self.faiss_index.ntotal} chunks")
    
    def search(self, query_vector: List[float], top_k: int = 8) -> List[Dict]:
        """
        向量检索
        
        Args:
            query_vector: 查询向量（来自 SentenceTransformer.encode()）
            top_k: 返回前 k 个结果
        
        Returns:
            检索结果列表（包含得分）
        """
        import numpy as np
        
        if not self.chunks:
            return []
        
        # 如果使用 Faiss
        if self.use_faiss and self.faiss_index:
            query_array = np.array([query_vector], dtype='float32')
            distances, indices = self.faiss_index.search(query_array, min(top_k, self.faiss_index.ntotal))
            
            ranked = []
            for idx, distance in zip(indices[0], distances[0]):
                chunk = self.chunks[idx]
                # L2 距离转相似度分数 (0-1)
                similarity = 1.0 / (1.0 + float(distance))
                ranked.append({
                    "chunk_id": chunk.chunk_id,
                    "trial_id": chunk.trial_id,
                    "chunk_type": chunk.chunk_type,
                    "text": chunk.text,
                    "metadata": chunk.metadata,
                    "score": similarity,
                })
            return ranked
        
        # 备用：手动计算余弦相似度（如果不用 Faiss）
        else:
            query_vec_norm = math.sqrt(sum(v * v for v in query_vector))
            if query_vec_norm == 0:
                return []
            
            ranked = []
            for chunk in self.chunks:
                # 计算余弦相似度
                dot_product = sum(q * c for q, c in zip(query_vector, chunk.vector))
                chunk_norm = math.sqrt(sum(v * v for v in chunk.vector))
                
                if chunk_norm == 0:
                    similarity = 0.0
                else:
                    similarity = dot_product / (query_vec_norm * chunk_norm)
                
                ranked.append({
                    "chunk_id": chunk.chunk_id,
                    "trial_id": chunk.trial_id,
                    "chunk_type": chunk.chunk_type,
                    "text": chunk.text,
                    "metadata": chunk.metadata,
                    "score": similarity,
                })
            
            ranked.sort(key=lambda x: x["score"], reverse=True)
            return ranked[:top_k]
    
    def save(self, path: str):
        """保存索引（JSON 格式）"""
        payload = {
            "dim": self.dim,
            "chunks": [asdict(c) for c in self.chunks],
            "use_faiss": self.use_faiss,
        }
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ 索引已保存: {path}")
    
    @classmethod
    def load(cls, path: str) -> "TrialVectorIndex":
        """加载索引"""
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        index = cls(dim=payload.get("dim", 384), use_faiss=payload.get("use_faiss", True))
        for item in payload.get("chunks", []):
            index.chunks.append(CriterionChunk(**item))
        print(f"✅ 索引已加载: {len(index.chunks)} chunks")
        return index


class VectorSearcher:
    """
    使用 Faiss 索引进行高效向量检索
    
    用法：
        searcher = VectorSearcher(
            faiss_index_path='structured_data/vector_index/trials.faiss',
            metadata_path='structured_data/vector_index/metadata.json'
        )
        results = searcher.search(query_text, top_k=20)
    """
    
    def __init__(self, faiss_index_path: str, metadata_path: str, 
                 model_name: str = 'GanymedeNil/text2vec-large-chinese'):
        """
        初始化向量搜索器
        
        Args:
            faiss_index_path: Faiss 索引文件路径
            metadata_path: 元数据 JSON 文件路径
            model_name: SentenceTransformer 模型名称
        """
        try:
            import faiss
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError("请先安装: pip install faiss-cpu sentence-transformers")
        
        # 加载模型
        self.model = SentenceTransformer(model_name)
        
        # 加载 Faiss 索引
        index_path = Path(faiss_index_path)
        if not index_path.exists():
            raise FileNotFoundError(f"找不到 Faiss 索引: {faiss_index_path}")
        
        self.index = faiss.read_index(str(index_path))
        
        # 加载元数据
        metadata_path = Path(metadata_path)
        if not metadata_path.exists():
            raise FileNotFoundError(f"找不到元数据: {metadata_path}")
        
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        self.trial_ids = metadata.get('trial_ids', [])
        self.trial_names = metadata.get('trial_names', [])
        self.embedding_dim = metadata.get('embedding_dim', 384)
        
        print(f"✅ VectorSearcher 已初始化")
        print(f"   - 试验数: {len(self.trial_ids)}")
        print(f"   - 向量维度: {self.embedding_dim}")
        print(f"   - 模型: {model_name}")
    
    def search(self, query_text: str, top_k: int = 20) -> List[Dict]:
        """
        检索最相似的试验
        
        Args:
            query_text: 查询文本（患者信息或病情描述）
            top_k: 返回前 k 个结果
        
        Returns:
            检索结果列表
            [
                {
                    'trial_id': '...',
                    'trial_name': '...',
                    'vector_score': 0.85,
                }
            ]
        """
        import numpy as np
        
        # 对查询文本进行向量化
        query_vector = self.model.encode([query_text], batch_size=1)[0]
        query_vector = query_vector.astype('float32').reshape(1, -1)
        
        # Faiss 检索（L2 距离）
        distances, indices = self.index.search(query_vector, min(top_k, self.index.ntotal))
        
        results = []
        for idx, distance in zip(indices[0], distances[0]):
            # L2 距离转相似度分数 (0-1)
            # 距离越小，相似度越高
            similarity = 1.0 / (1.0 + float(distance))
            
            results.append({
                'trial_id': self.trial_ids[idx],
                'trial_name': self.trial_names[idx],
                'vector_score': similarity,
                'distance': float(distance),
            })
        
        return results
    
    def batch_search(self, query_texts: List[str], top_k: int = 20) -> List[List[Dict]]:
        """
        批量检索（多个患者）
        
        Args:
            query_texts: 查询文本列表
            top_k: 返回前 k 个结果
        
        Returns:
            检索结果列表的列表
        """
        import numpy as np
        
        # 批量向量化（更高效）
        query_vectors = self.model.encode(query_texts, batch_size=32)
        query_vectors = query_vectors.astype('float32')
        
        # Faiss 批量检索
        distances, indices = self.index.search(query_vectors, min(top_k, self.index.ntotal))
        
        all_results = []
        for query_idx, (dist_row, idx_row) in enumerate(zip(distances, indices)):
            results = []
            for idx, distance in zip(idx_row, dist_row):
                similarity = 1.0 / (1.0 + float(distance))
                results.append({
                    'trial_id': self.trial_ids[idx],
                    'trial_name': self.trial_names[idx],
                    'vector_score': similarity,
                    'distance': float(distance),
                })
            all_results.append(results)
        
        return all_results
