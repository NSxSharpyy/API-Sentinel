CC ?= cc
CFLAGS ?= -O2 -g
WARNINGS := -Wall -Wextra -Werror
LIBBPF_CFLAGS := $(shell pkg-config --cflags libbpf)
LIBBPF_LIBS := $(shell pkg-config --libs libbpf)

.PHONY: all clean

all: blocklist_map_ctl

blocklist_map_ctl: map_ctl.c blocklist_map.h
	$(CC) $(CFLAGS) $(WARNINGS) $(LIBBPF_CFLAGS) \
		map_ctl.c -o $@ $(LIBBPF_LIBS)

clean:
	rm -f blocklist_map_ctl
