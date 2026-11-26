import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_sessionstart(session):
    """测试前重建 seed 数据与数据库"""
    from dotenv import load_dotenv

    load_dotenv()
    from scripts.build_seed_data import main as build_seed
    from scripts.init_db import main as init_db

    build_seed()
    init_db(force=True)
