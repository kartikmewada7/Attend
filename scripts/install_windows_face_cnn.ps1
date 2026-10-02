# Run this from a VS 2022 Developer PowerShell / x64 Native Tools prompt.
$ErrorActionPreference = "Stop"

if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) {
  throw "cl.exe not found. Install Visual Studio Build Tools with Desktop development with C++, MSVC and Windows SDK, then reopen Developer PowerShell."
}

Write-Host "MSVC:"
cl 2>&1 | Select-Object -First 2

python -m pip install --upgrade pip
python -m pip install dlib==20.0.1
python -m pip install -r requirements.txt
python -c "import dlib, face_recognition; print("FACE CNN STACK OK", dlib.__version__)"
