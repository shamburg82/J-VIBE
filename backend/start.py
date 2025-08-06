# backend/start.py - Simple startup script
"""
Simple startup script that handles both local and Posit environments.
Run this file directly or use with uvicorn.
"""

import os
import sys
from pathlib import Path

# Add the backend directory to Python path if needed
backend_dir = Path(__file__).parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Now import and run the app
if __name__ == "__main__":
    # Import after path setup
    from main import app
    import uvicorn
    
    # Get port from environment or default
    port = int(os.getenv("PORT", "8000"))
    
    # Check if we're in Posit Workbench
    is_workbench = bool(os.getenv("RS_SERVER_URL")) and not bool(os.getenv("RSTUDIO_CONNECT_URL"))
    is_connect = bool(os.getenv("RSTUDIO_CONNECT_URL"))
    
    if is_connect:
        print("🚀 Running on Posit Connect")
        # Posit Connect will handle the server startup
        pass
    elif is_workbench:
        print("🚀 Running on Posit Workbench")
        # Get root path for Workbench
        import subprocess
        try:
            result = subprocess.run(
                f'echo $(/usr/lib/rstudio-server/bin/rserver-url -l {port})',
                stdout=subprocess.PIPE,
                shell=True,
                timeout=10
            )
            root_path = result.stdout.decode().strip() if result.returncode == 0 else ""
            print(f"📁 Root path: {root_path}")
        except Exception as e:
            print(f"⚠️ Warning: Could not get root path: {e}")
            root_path = ""
        
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            root_path=root_path,
            log_level="info"
        )
    else:
        print("🚀 Running locally")
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            log_level="info",
            reload=True
        )
