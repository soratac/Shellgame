FROM debian:bookworm-slim AS player-bash
# Build the player's interactive shell from the signed Debian source archive.
# Service scripts and system tools keep the distribution's /bin/bash.
RUN sed -i 's/^Types: deb$/Types: deb deb-src/' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
       build-essential libncurses-dev dpkg-dev patch \
    && mkdir /src && cd /src && apt-get source bash
COPY build/bash-game-input.patch /tmp/
RUN cd /src/bash-*/ && patch -p1 < /tmp/bash-game-input.patch \
    && ./configure --prefix=/usr --without-bash-malloc --disable-nls \
    && make -j2 bash && install -s -m755 bash /usr/local/bin/frost-bash

RUN apt-get update && apt-get install -y --no-install-recommends libseccomp-dev
COPY build/frost-login.c /src/frost-login.c
RUN cc -O2 -Wall -Wextra -Werror /src/frost-login.c -lseccomp -o /usr/local/bin/frost-login

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-server python3 python3-pyte bash-completion ca-certificates \
    socat libseccomp2 less nano vim-tiny procps findutils gawk coreutils grep sed tree python3-paramiko \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 -s /usr/local/bin/frost-login player \
    && useradd -M -u 1001 -d /home/player -s /bin/sh score \
    && install -d -m 700 /var/lib/frost /var/lib/frost-private /var/lib/frost-private/saved \
    && rm -f /etc/ssh/ssh_host_* \
    && passwd -l root \
    && rm /etc/shadow && ln -s /run/frost/shadow /etc/shadow
ENV PYTHONPATH=/opt/frost LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=player-bash /usr/local/bin/frost-bash /usr/local/bin/frost-bash
COPY frost /opt/frost/frost
RUN python3 /opt/frost/frost/sound/compose.py /opt/frost/frost/sound/winter.wav
COPY world /opt/frost/world
COPY shell /etc/frost
COPY bin /usr/local/bin
COPY --from=player-bash /usr/local/bin/frost-login /usr/local/bin/frost-login
RUN chmod 755 /usr/local/bin/* \
    && chmod -R a+rX /opt/frost /etc/frost \
    && chown player:player /home/player \
    && python3 -c "import site; from pathlib import Path; (Path(site.getsitepackages()[0])/'frost.pth').write_text('/opt/frost\\n')"
RUN useradd -M -u 1002 -d /run/frost -s /bin/sh krampus
WORKDIR /
EXPOSE 22 8080
ENTRYPOINT ["/usr/local/bin/entrypoint"]
CMD ["player"]
