import os
import pickle

def save_embeddings_atomically(pkl_path, new_data):
    """임시 파일 생성 후 os.replace()로 쓰기 도중 파일 손상 방지"""
    tmp_path = f"{pkl_path}.tmp"
    
    with open(tmp_path, "wb") as f:
        pickle.dump(new_data, f)
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp_path, pkl_path)