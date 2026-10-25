CC ?= cc
CLANG ?= clang
CFLAGS ?= -O2 -g
WARNINGS := -Wall -Wextra -Werror
LIBBPF_CFLAGS := $(shell pkg-config --cflags libbpf)
LIBBPF_LIBS := $(shell pkg-config --libs libbpf)
BPF_CFLAGS := -O2 -g -target bpf -D__TARGET_ARCH_x86 -Wall -Werror \
              -I/usr/include/x86_64-linux-gnu -I.

.PHONY: all clean

all: blocklist_map_ctl blocklist_enforce.bpf.o blocklist_enforcer_loader

blocklist_map_ctl: map_ctl.c blocklist_map.h
	$(CC) $(CFLAGS) $(WARNINGS) $(LIBBPF_CFLAGS) \
		map_ctl.c -o $@ $(LIBBPF_LIBS)

blocklist_enforce.bpf.o: blocklist_enforce.bpf.c blocklist_map.h
	$(CLANG) $(BPF_CFLAGS) -c $< -o $@

blocklist_enforcer_loader: blocklist_enforcer_loader.c blocklist_map.h
	$(CC) $(CFLAGS) $(WARNINGS) $(LIBBPF_CFLAGS) $< -o $@ $(LIBBPF_LIBS)

clean:
	rm -f blocklist_map_ctl blocklist_enforce.bpf.o blocklist_enforcer_loader
