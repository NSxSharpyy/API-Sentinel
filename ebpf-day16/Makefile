CLANG ?= clang
CC ?= gcc

BPF_CFLAGS := -O2 -g -target bpf -D__TARGET_ARCH_x86 -Wall -Werror \
              -I/usr/include/x86_64-linux-gnu -I.
USER_CFLAGS := -O2 -g -Wall -Wextra -Werror
LIBBPF_CFLAGS := $(shell pkg-config --cflags libbpf)
LIBBPF_LIBS := $(shell pkg-config --libs libbpf)

.PHONY: all clean
all: packet_capture.bpf.o loader

packet_capture.bpf.o: packet_capture.bpf.c api_sentinel_event.h
	$(CLANG) $(BPF_CFLAGS) -c packet_capture.bpf.c -o packet_capture.bpf.o

loader: loader.c
	$(CC) $(USER_CFLAGS) $(LIBBPF_CFLAGS) loader.c -o loader $(LIBBPF_LIBS)

clean:
	rm -f packet_capture.bpf.o loader
