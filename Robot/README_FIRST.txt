BX1 ROBOT GITHUB DEPLOYMENT
============================

Purpose
-------
Builds a fresh Python environment for the GitHub copy at:

  /home/arduino/BX1_Robot_GitHub/Robot

It does not delete or overwrite the existing project at:

  /home/arduino/Arduino_Q_Client_V1

Installation
------------
1. Drag this ZIP into:

     /home/arduino/BX1_Robot_GitHub/Robot

2. In PuTTY, run:

     cd /home/arduino/BX1_Robot_GitHub/Robot
     unzip -o BX1_Robot_GitHub_Deployment.zip
     chmod +x INSTALL_BX1_GITHUB.sh ROLLBACK_TO_OLD_BX1.sh VERIFY_BX1_GITHUB.sh
     ./INSTALL_BX1_GITHUB.sh

3. The installer will:
   - create a fresh .venv
   - install dependencies
   - copy robot configuration/models from the old installation
   - create bx1-github.service
   - disable the old BX1 startup service
   - enable the new application at boot
   - confirm whether it started successfully

Verification
------------
Run:

  ./VERIFY_BX1_GITHUB.sh

Rollback
--------
Run:

  ./ROLLBACK_TO_OLD_BX1.sh

Future GitHub updates
---------------------
Run:

  cd /home/arduino/BX1_Robot_GitHub
  git pull
  sudo systemctl restart bx1-github.service

Important
---------
The installer may take several minutes while Linux and Python packages install.
Do not power off the robot during installation.
