# backend/app.py (Posit Connect/Workbench entry point)
"""
Posit Connect/Workbench entry point for FastAPI application.
This file is required for Posit Connect to recognize the FastAPI app.
"""

import os
import subprocess
from app.main import app

def get_posit_root_path(port: int = 8000) -> str:
    """Get root path for Posit Workbench."""
    
    if 'RS_SERVER_URL' not in os.environ or not os.environ['RS_SERVER_URL']:
        return ''
    
    try:
        result = subprocess.run(
            f'echo $(/usr/lib/rstudio-server/bin/rserver-url -l {port})', 
            stdout=subprocess.PIPE, 
            shell=True,
            timeout=10
        )
        
        if result.returncode == 0:
            path = result.stdout.decode().strip()
            print(f"✅ Posit Workbench root path: {path}")
            return path
        else:
            print(f"⚠️  Failed to get root path, return code: {result.returncode}")
            return ''
            
    except Exception as e:
        print(f"⚠️  Error getting Posit Workbench root path: {e}")
        return ''

# Posit Connect will look for 'app' variable
# This is the ASGI application that will be served
if __name__ == "__main__":
    import uvicorn
    
    port = 8000
    
    # Detect environment
    is_connect = bool(os.getenv("RSTUDIO_CONNECT_URL"))
    is_workbench = bool(os.getenv("RS_SERVER_URL")) and not is_connect
    
    if is_connect:
        print("🚀 Starting on Posit Connect (Production)")
        # Posit Connect handles the server setup
        pass
    elif is_workbench:
        print("🚀 Starting on Posit Workbench (Development)")
        root_path = get_posit_root_path(port)
        
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=port,
            root_path=root_path,
            log_level="debug",
            reload=True
        )
    else:
        print("🚀 Starting in other environment")
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=port,
            log_level="info"
        )
