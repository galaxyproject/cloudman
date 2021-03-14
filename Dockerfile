FROM ubuntu:20.04 as stage1

ARG DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED 1

ENV KUBE_LATEST_VERSION=v1.20.0
ENV HELM_VERSION=v3.5.2
ENV HELM_FILENAME=helm-${HELM_VERSION}-linux-amd64.tar.gz

RUN set -xe; \
    apt-get -qq update && apt-get install -y --no-install-recommends \
        apt-transport-https \
        git-core \
        make \
        software-properties-common \
        gcc \
        python3-dev \
        libffi-dev \
        python3-pip \
        python3-setuptools \
        curl \
    && curl -L https://storage.googleapis.com/kubernetes-release/release/${KUBE_LATEST_VERSION}/bin/linux/amd64/kubectl -o /usr/local/bin/kubectl \
    && curl -L https://get.helm.sh/${HELM_FILENAME} | tar xz && mv linux-amd64/helm /usr/local/bin/helm && rm -rf linux-amd64 \
    && apt-get autoremove -y && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* \
    && mkdir -p /app \
    && pip3 install virtualenv \
    && virtualenv -p python3 --prompt "(cloudman)" /app/venv

# Set working directory to /app/
WORKDIR /app/

# Only add files required for installation to improve build caching
ADD requirements.txt /app
ADD setup.py /app
ADD README.rst /app
ADD HISTORY.rst /app
ADD cloudman/cloudman/__init__.py /app/cloudman/cloudman/__init__.py

# Install requirements. Move this above ADD as 'pip install cloudman-server'
# asap so caching works
RUN /app/venv/bin/pip3 install -U pip && /app/venv/bin/pip3 install --no-cache-dir -r requirements.txt


# Stage-2
FROM ubuntu:20.04

ARG DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED 1

# Create cloudman user environment
RUN useradd -ms /bin/bash cloudman \
    && mkdir -p /app \
    && chown cloudman:cloudman /app -R \
    && apt-get -qq update && apt-get install -y --no-install-recommends \
        git-core \
        python3-pip \
        python3-setuptools \
        locales locales-all \
    && apt-get autoremove -y && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/*

ENV LC_ALL en_US.UTF-8

WORKDIR /app/cloudman/

# Copy cloudman files to final image
COPY --chown=cloudman:cloudman --from=stage1 /app /app
COPY --chown=cloudman:cloudman --from=stage1 /usr/local/bin/kubectl /usr/local/bin/kubectl
COPY --chown=cloudman:cloudman --from=stage1 /usr/local/bin/helm /usr/local/bin/helm

# Add the source files last to minimize layer cache invalidation
ADD --chown=cloudman:cloudman . /app

# Switch to new, lower-privilege user
USER cloudman

RUN chmod a+x /usr/local/bin/kubectl \
    && chmod a+x /usr/local/bin/helm \
    && /app/venv/bin/python manage.py collectstatic --no-input

# gunicorn will listen on this port
EXPOSE 8000

CMD /bin/bash -c "source /app/venv/bin/activate && /app/venv/bin/gunicorn -k gevent -b :8000 --access-logfile - --error-logfile - --log-level info cloudman.wsgi"
