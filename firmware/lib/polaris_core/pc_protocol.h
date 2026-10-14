// Command parsing and time formatting. Mirror of polaris_gs/core/protocol.py.
#pragma once

#include <stddef.h>

namespace proto {

enum class Cmd { NONE, SAT, MODE, WARP, VEH, VEH_OFF, JOG, HOME, STOW, ACK, COMP };

struct Command {
  Cmd cmd = Cmd::NONE;
  long sat = 0;
  char mode[8] = {0};
  int warp = 0;
  double roll = 0, pitch = 0, yaw = 0;
  char axis[3] = {0};
  double jogDeg = 0;
  bool comp = true;
};

constexpr double MAX_JOG_DEG = 90.0;
constexpr double MAX_TILT_DEG = 45.0;

// Returns nullptr on success, otherwise a short reason (same text as Python)
const char* parseCommand(const char* line, Command& out);

// "2026-10-14T22:05:03.1Z"
void isoUtc(double tUnix, char* buf, size_t n);

// Copy keeping only safe printable characters (for echo in JSON)
void sanitize(const char* in, char* out, size_t n);

}  // namespace proto
