<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <link rel="icon" href="%PUBLIC_URL%/favicon.ico" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="theme-color" content="#1976d2" />
    <meta name="description" content="JazzVIBE - Visual Interface for Biostatistical Exploration" />
    <link rel="apple-touch-icon" href="%PUBLIC_URL%/logo192.png" />
    <link rel="manifest" href="%PUBLIC_URL%/manifest.json" />
    
    <!-- Material-UI Roboto Font -->
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      rel="stylesheet"
      href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;600;700&display=swap"
    />
    
    <!-- Material Icons -->
    <link
      rel="stylesheet"
      href="https://fonts.googleapis.com/icon?family=Material+Icons"
    />
    
    <title>JazzVIBE</title>
    
    <!-- Dynamic base path handling - Server will inject if needed -->
    <script>
      // This script runs before React loads to set up base path detection
      (function() {
        // Only run client-side detection if server didn't provide path
        if (!window.__POSIT_BASE_PATH__) {
          var pathname = window.location.pathname;
          var basePath = '';
          
          console.log('Client-side base path detection for:', pathname);
          
          // Posit Workbench pattern: /s/{session}/p/{port}/
          var workbenchMatch = pathname.match(/^(\/s\/[^\/]+\/p\/[^\/]+)/);
          if (workbenchMatch) {
            basePath = workbenchMatch[1];
            console.log('Detected Workbench base path:', basePath);
          }
          // Posit Connect pattern - more flexible
          else if (pathname.indexOf('/connect/') === 0) {
            var connectMatch = pathname.match(/^(\/connect\/[^\/]*)/);
            if (connectMatch) {
              basePath = connectMatch[1];
              console.log('Detected Connect base path:', basePath);
            }
          }
          
          if (basePath) {
            window.__POSIT_BASE_PATH__ = basePath;
            console.log('Client set base path:', window.__POSIT_BASE_PATH__);
          } else {
            console.log('No base path detected, using root');
          }
        } else {
          console.log('Using server-provided base path:', window.__POSIT_BASE_PATH__);
        }
      })();
    </script>
    
    <style>
      /* Loading screen styles */
      .loading-screen {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-color: #f5f5f5;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        z-index: 9999;
        font-family: 'Roboto', sans-serif;
      }
      
      .loading-spinner {
        width: 40px;
        height: 40px;
        border: 4px solid #e0e0e0;
        border-top: 4px solid #1976d2;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin-bottom: 16px;
      }
      
      @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
      }
      
      .loading-text {
        font-size: 18px;
        color: #666;
        margin: 8px 0;
      }
      
      .loading-debug {
        font-size: 12px;
        color: #999;
        margin-top: 16px;
        max-width: 400px;
        text-align: center;
      }
      
      /* Hide loading screen when React app loads */
      #root:not(:empty) + .loading-screen {
        display: none;
      }
      
      /* Error state for loading screen */
      .loading-screen.error {
        background-color: #ffebee;
      }
      
      .loading-screen.error .loading-text {
        color: #c62828;
      }
    </style>
  </head>
  <body>
    <noscript>You need to enable JavaScript to run this app.</noscript>
    <div id="root"></div>
    
    <!-- Loading screen shown while React app loads -->
    <div id="loading-screen" class="loading-screen">
      <div class="loading-spinner"></div>
      <div class="loading-text">Loading JazzVIBE...</div>
      <div class="loading-debug">
        <div id="loading-debug-info">Initializing application...</div>
      </div>
    </div>
    
    <script>
      // Enhanced loading screen with debug info
      (function() {
        var debugInfo = document.getElementById('loading-debug-info');
        var loadingScreen = document.getElementById('loading-screen');
        
        if (debugInfo) {
          var info = [
            'URL: ' + window.location.href,
            'Path: ' + window.location.pathname,
            'Base: ' + (window.__POSIT_BASE_PATH__ || 'none')
          ];
          debugInfo.innerHTML = info.join('<br>');
        }
        
        // Auto-hide loading screen if React doesn't load within 30 seconds
        setTimeout(function() {
          if (loadingScreen && loadingScreen.style.display !== 'none') {
            loadingScreen.classList.add('error');
            if (debugInfo) {
              debugInfo.innerHTML = 'Loading timeout - please refresh the page<br>' + debugInfo.innerHTML;
            }
          }
        }, 30000);
      })();
    </script>
    
    <!-- 
      This HTML file is a template.
      If you open it directly in the browser, you will see an empty page.
      
      You can add webfonts, meta tags, or analytics to this file.
      The build step will place the bundled scripts into the <body> tag.
      
      To begin the development, run `npm start` or `yarn start`.
      To create a production bundle, use `npm run build` or `yarn build`.
    -->
  </body>
</html>
