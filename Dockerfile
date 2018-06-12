FROM python:3.6-alpine

ENV PYTHONUNBUFFERED 1

# Env vars required for correct cloudman bootup
# ENV RANCHER_URL
# ENV RANCHER_TOKEN
# ENV RANCHER_CLUSTER_ID
# ENV RANCHER_PROJECT_ID

ENV KUBE_LATEST_VERSION=v1.10.4
ENV HELM_VERSION=v2.9.1
ENV HELM_FILENAME=helm-${HELM_VERSION}-linux-amd64.tar.gz

RUN apk update \
    # psycopg2 dependencies
    && apk add --no-cache --virtual build-deps gcc python3-dev musl-dev \
    && apk add --no-cache postgresql-dev \
    # CFFI dependencies
    && apk --no-cache add libffi-dev py-cffi \
    # git for cloning requirements dependencies
    && apk --no-cache add git \
    # For pynacl
    && apk --no-cache add make linux-headers \
    \
    # Install latest kubectl & helm
    && apk add --no-cache curl \
    && curl -L https://storage.googleapis.com/kubernetes-release/release/${KUBE_LATEST_VERSION}/bin/linux/amd64/kubectl -o /usr/local/bin/kubectl \
    && curl -L https://storage.googleapis.com/kubernetes-helm/${HELM_FILENAME} | tar xz && mv linux-amd64/helm /bin/helm && rm -rf linux-amd64 \
    && chmod +x /usr/local/bin/kubectl \
    && rm /var/cache/apk/*

# Create cloudman user environment
RUN adduser -D -g '' cloudman \
    && mkdir -p /app

# Set working directory to /app/
WORKDIR /app/

# Add files to /app/
ADD . /app

# Install requirements. Move this above ADD as 'pip install cloudman-server'
# asap so caching works
RUN pip install --no-cache-dir -r requirements.txt

#RUN python django-cloudman/manage.py collectstatic --no-input

# Change ownership to cloudman
RUN chown -R cloudman:cloudman /app

# Switch to new, lower-privilege user
USER cloudman

# gunicorn will listen on this port
EXPOSE 8000

CMD gunicorn -b :8000 --access-logfile - --error-logfile - --log-level debug cloudman.wsgi