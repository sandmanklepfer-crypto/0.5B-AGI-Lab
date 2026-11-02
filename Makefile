CC      ?= gcc
CFLAGS  ?= -O2 -fPIC -Wall -Wextra -Wno-unused-parameter
LDFLAGS ?= -shared
LDLIBS  ?= -ldl

TARGET  := fakesock.so
SRC     := src/fakesock.c

.PHONY: all clean install test

all: $(TARGET)

$(TARGET): $(SRC)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $< $(LDLIBS)

clean:
	rm -f $(TARGET)

install: $(TARGET)
	install -m 0644 $(TARGET) /usr/local/lib/$(TARGET)

# 抽象 socket 不会落地成文件，只能从 /proc/net/unix 看
test:
	@echo "=== 抽象 Wayland socket ==="
	@grep "@" /proc/net/unix | sed 's/.*@/@/' | sort -u | grep TLWL || \
	  echo "(没有，合成器还没跑起来)"
