// WAV helpers for Chromium's fake microphone (--use-file-for-fake-audio-capture), which loops the file.
import { readFileSync, writeFileSync } from "node:fs";

function readWav(path) {
  const buf = readFileSync(path);
  if (buf.toString("ascii", 0, 4) !== "RIFF" || buf.toString("ascii", 8, 12) !== "WAVE") throw new Error(`${path} is not WAV`);
  let offset = 12;
  let fmt = null;
  let data = null;
  while (offset + 8 <= buf.length) {
    const id = buf.toString("ascii", offset, offset + 4);
    const size = buf.readUInt32LE(offset + 4);
    const body = offset + 8;
    if (id === "fmt ") {
      fmt = {
        channels: buf.readUInt16LE(body + 2),
        sampleRate: buf.readUInt32LE(body + 4),
        bitsPerSample: buf.readUInt16LE(body + 14),
      };
    } else if (id === "data") {
      data = buf.subarray(body, Math.min(body + size, buf.length));
    }
    offset = body + size + (size % 2);
  }
  if (!fmt || !data) throw new Error(`${path}: missing fmt or data chunk`);
  return { ...fmt, data };
}

function writeWav(path, { channels, sampleRate, bitsPerSample, data }) {
  const header = Buffer.alloc(44);
  const blockAlign = (channels * bitsPerSample) / 8;
  header.write("RIFF", 0, "ascii");
  header.writeUInt32LE(36 + data.length, 4);
  header.write("WAVE", 8, "ascii");
  header.write("fmt ", 12, "ascii");
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20); // PCM
  header.writeUInt16LE(channels, 22);
  header.writeUInt32LE(sampleRate, 24);
  header.writeUInt32LE(sampleRate * blockAlign, 28);
  header.writeUInt16LE(blockAlign, 32);
  header.writeUInt16LE(bitsPerSample, 34);
  header.write("data", 36, "ascii");
  header.writeUInt32LE(data.length, 40);
  writeFileSync(path, Buffer.concat([header, data]));
}

/** Speech followed by silence, so a recording longer than the clip does not pick up a repeat of the sentence. */
export function padWithSilence(input, output, seconds) {
  const wav = readWav(input);
  const blockAlign = (wav.channels * wav.bitsPerSample) / 8;
  const silence = Buffer.alloc(Math.round(seconds * wav.sampleRate) * blockAlign);
  writeWav(output, { ...wav, data: Buffer.concat([wav.data, silence]) });
  return { speechSeconds: wav.data.length / (wav.sampleRate * blockAlign), totalSeconds: wav.data.length / (wav.sampleRate * blockAlign) + seconds };
}

export function writeSilence(output, seconds, sampleRate = 16000) {
  writeWav(output, { channels: 1, sampleRate, bitsPerSample: 16, data: Buffer.alloc(seconds * sampleRate * 2) });
}
