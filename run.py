"""
启动脚本 - 允许从局域网访问
"""
from dotenv import load_dotenv

load_dotenv()

import uvicorn

if __name__ == "__main__":
    # 绑定到 0.0.0.0 允许从局域网访问
    # host: 0.0.0.0 表示监听所有网络接口
    # port: 8000 是默认端口，可以根据需要修改
    uvicorn.run(
        "main:app",
        host="0.0.0.0",  # 允许从局域网访问
        port=8000,
        reload=True,  # 开发模式，代码修改自动重载
    )

