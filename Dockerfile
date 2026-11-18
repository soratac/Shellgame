FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-server python3 python3-pyte bash-completion ca-certificates \
    less nano vim-tiny procps findutils gawk coreutils grep sed tree python3-paramiko \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 -s /bin/bash player \
    && useradd -M -u 1001 -d /home/player -s /bin/sh score \
    && install -d -m 700 /var/lib/frost \
    && rm -f /etc/ssh/ssh_host_* \
    && passwd -l root \
    && rm /etc/shadow && ln -s /run/frost/shadow /etc/shadow
ENV PYTHONPATH=/opt/frost LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY frost /opt/frost/frost
COPY world /opt/frost/world
COPY shell /etc/frost
COPY bin /usr/local/bin
RUN chmod 755 /usr/local/bin/* \
    && chmod -R a+rX /opt/frost /etc/frost \
    && chown player:player /home/player \
    && python3 -c "import site; from pathlib import Path; (Path(site.getsitepackages()[0])/'frost.pth').write_text('/opt/frost\\n')"
WORKDIR /home/player
EXPOSE 22 8080
ENTRYPOINT ["/usr/local/bin/entrypoint"]
CMD ["player"]
