controller: rescile-ce serve
runner: if [ ! -x ./rescile-runner ]; then gh release download latest -R rescile/rescile-runner -p rescile-runner-x86_64-linux-musl -O rescile-runner && chmod +x rescile-runner; fi && ./rescile-runner -m daemon --debug --listen 127.0.0.1:3000
