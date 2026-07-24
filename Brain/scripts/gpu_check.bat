@echo off
echo ================================
echo NVIDIA GPU
echo ================================
nvidia-smi

echo.
echo ================================
echo Ollama loaded models
echo ================================
ollama ps

echo.
echo If Ollama says 100%% CPU, it is not using the NVIDIA GPU.
echo Update your NVIDIA/Dell driver, restart Windows, then test again.
pause
