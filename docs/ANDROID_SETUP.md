# Android-only setup (no PC)

## A. Try it first without a server (development mode)
1. In GitHub (mobile browser, desktop-site mode helps): New repository, then Add file, Upload files. Upload the unzipped project.
2. Open the repository, Code, Codespaces, Create codespace. In its terminal run:
   `pip install -r requirements.txt && python wsgi.py`
3. Open the forwarded port 8000. Register the first account (it becomes the owner).
4. Open **Server** and choose "Development environment". It is not a permanent VPS: it stops when idle.

## B. Real server
You must do these on the provider's website and on the server; the dashboard cannot do them:
1. Create the account and the VPS at the provider (see the in-app page "Free server options and limits"). Choose Ubuntu 22.04/24.04. Add your SSH key or use the provider's browser console.
2. Open the server's terminal (the provider's web console, or an SSH app such as Termux/JuiceSSH).
3. `git clone https://github.com/YOU/YOUR-REPO.git && cd YOUR-REPO && sudo bash deploy/install.sh http://SERVER_IP`
4. Open the provider firewall for ports 80 and 443 (on Oracle: VCN security list).
5. Open the address, register the first account, open **Server**, choose "Real VPS or server".
6. For HTTPS, point a domain at the server and run certbot (the installer prints the command), then change `BASE_URL` in `/etc/modyx/env` to https and set `COOKIE_SECURE=true`, then `sudo systemctl restart modyx`.

## What the dashboard manages after setup
Server status and metrics, projects and their folders. File manager, terminal, GitHub and deployments arrive in later phases.
