import winreg
import sys
import os

# 定义我们应用在注册表中的名称
APP_NAME = "ClipboardHistory"

# 注册表路径
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"

def get_run_command():
    """获取启动命令，自动检测是打包环境还是开发环境"""
    if getattr(sys, 'frozen', False):
        # 打包环境：使用exe文件
        app_path = sys.executable
        return f'"{app_path}"'
    else:
        # 开发环境：使用pythonw.exe运行main.py
        python_exe = sys.executable
        app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'main.py'))
        
        # 更加健壮地替换 python.exe 为 pythonw.exe (不区分大小写)
        dir_name = os.path.dirname(python_exe)
        pythonw_exe = os.path.join(dir_name, "pythonw.exe")
        
        if not os.path.exists(pythonw_exe):
            # 如果找不到 pythonw，则退而求其次使用 python
            pythonw_exe = python_exe
            
        return f'"{pythonw_exe}" "{app_path}"'

def add_to_startup():
    """将本应用添加到开机启动项"""
    try:
        run_command = get_run_command()
        # 打开注册表项，如果不存在则创建
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH)
        # 设置值
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, run_command)
        winreg.CloseKey(key)
        print(f"Successfully added '{APP_NAME}' to startup with command: {run_command}")
        return True
    except OSError as e:
        print(f"Error adding to startup: {e}")
        return False

def remove_from_startup():
    """从开机启动项中移除本应用"""
    try:
        # 打开注册表项
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_ALL_ACCESS)
        # 删除值
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
        print(f"Successfully removed '{APP_NAME}' from startup.")
        return True
    except OSError:
        # 如果值不存在，会抛出OSError，这是正常的，说明已经移除了
        print(f"'{APP_NAME}' was not in startup, nothing to do.")
        return True

def is_in_startup():
    """检查本应用是否已在开机启动项中"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        # 键或值不存在
        return False
    except OSError:
        # 键或值不存在
        return False

if __name__ == '__main__':
    # 用于直接测试
    print(f"Is in startup? {is_in_startup()}")
    print("Adding to startup...")
    add_to_startup()
    print(f"Is in startup? {is_in_startup()}")
    print("Removing from startup...")
    remove_from_startup()
    print(f"Is in startup? {is_in_startup()}")
