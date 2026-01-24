# Controller

[中文简介](README_zh.md) | [Lireo](/Frank-qwq)

## What is **Controller**  
A simple alternative to SSH that allows you to access and control another computer's command-line operations.  

## Download the Project  
```bash  
git clone https://github.com/Frank-qwq/Controller  
cd Controller  
```  

## Server Deployment  
> **Notes**  
> 1. Ensure your server is accessible over the public network.  
> 2. Supported operating systems: Windows/Linux.  
> 3. Python 3.7 or higher is required.  

1. Set the server port (or skip this step to use the default port).  
    
    Open `server.py`.  

    $Line\ 591:$ Change `30003` in `def start_server(host='0.0.0.0', port=30003):` to your desired port.  

2. Start the server using the command:  
    ```bash  
    python server.py  
    ```  
    or  
    ```bash  
    python3 server.py  
    ```  
    You will then enter the Controller console.  

3. Type `?` and press Enter to view the usage of all commands.  

## Client Deployment  
> **Notes !important**  
> 1. Only Windows is supported.  
> 2. Python 3.7 or higher is required.  

### Set the Server Address  
Open `client.py`.  

$Line\ 190:$ In `host = 'your.server.ip'`, replace `your.server.ip` with your server's domain or IP address.  

$Line\ 191:$ In `port = 30003`, change `30003` to the port you specified (default is 30003, no change needed if using default).  

Don’t forget to save the file.  

<span id="pack-to-exe"></span>  
### Package into an EXE (Optional)  

Use the following command to package:  
> If you don’t have pyinstaller installed:  
> ```bash  
> pip install pyinstaller  
> ```  
```bash  
pyinstaller --noconfirm --onefile --windowed client.py  
```  

### Start with Python  
```bash  
python client.py  
```  

### Start with EXE  
[Package `client.py` into `client.exe`](#pack-to-exe)  

Double-click to run on the target machine (if applicable).  

Or start via command line:  
```bash  
client.exe  
```
