# Preparing the build environment
FROM golang:1.21-alpine AS builder
ENV GOFLAGS="-mod=readonly"
RUN apk add --update --no-cache bash ca-certificates curl git

# Download srcs
WORKDIR /
RUN git clone https://github.com/fclairamb/ftpserver.git --branch v0.13.0
WORKDIR /ftpserver

# Building
RUN CGO_ENABLED=0 go build -mod=readonly -ldflags='-w -s' -v -o ftpserver

# Preparing the final image
FROM ubuntu:22.04

WORKDIR /app
EXPOSE 2121-2130

COPY --from=builder /ftpserver/ftpserver /bin/ftpserver
COPY ftpserver.json /app/

ENTRYPOINT [ "/bin/ftpserver" ]
