# Controller

[English](README.md) | [Lireo](/Frank-qwq)

## 什么是 **Controller**
获取别人的电脑命令行操作，ssh的简单替代方案

## 下载项目
```bash
git clone https://github.com/Frank-qwq/Controller
cd Controller
```

## 服务端部署
> **注意事项**
> 1. 确保你的服务器能在公网上访问
> 2. 支持操作系统 Windows/Linux
> 3. 需要 Python 3.7 及以上版本运行

1. 设置服务器端口（或使用默认端口跳过这一步）
    
    打开 `server.py`

    $Line\ 591:$ 将 `def start_server(host='0.0.0.0', port=30003):` 中 `30003` 改为所需端口
2. 使用命令启动
    ```bash
    python server.py
    ```
    或
    ```
    python3 server.py
    ```
    即可进入Controller控制台
3. 输入 `?` 回车查看所有命令的使用方法

## 客户端部署
> **注意事项 !important**
> 1. 仅支持 Windows 系统
> 2. 需要 Python 3.7 +

### 设置服务器地址
打开 `client.py`

$Line\ 190:$ `host = 'your.server.ip'` 中，将 `your.server.ip` 改为你的服务器的域名或ip

$Line\ 191:$ `port = 30003` 中，将 `30003` 改为你指定的端口（默认为30003无需更改）

别忘记保存

<span id="pack-to-exe"></span>
### 打包成exe（按需选择）

使用命令打包
> 如果没有 pyinstaller
> ```bash
> pip install pyinstaller
> ```
```bash
pyinstaller --noconfirm --onefile --windowed client.py
```

### 使用 Python 启动
```bash
python client.py
```

### 使用 EXE 启动
[`client.py` 文件打包成 `client.exe`](#pack-to-exe)

直接在目标主机上双击启动（如果可行）

或使用命令行启动
```bash
client.exe
```