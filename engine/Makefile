CC = gcc
CFLAGS = -O3 -march=native -fPIC -shared -Wall -Wextra -std=c99
LDFLAGS = -lm
TARGET = libmiddleout.so

ifeq ($(shell uname), Darwin)
	TARGET = libmiddleout.dylib
endif

all: $(TARGET)

$(TARGET): middleout.c middleout.h
	$(CC) $(CFLAGS) middleout.c -o $(TARGET) $(LDFLAGS)

clean:
	rm -f $(TARGET) *.o

.PHONY: all clean
