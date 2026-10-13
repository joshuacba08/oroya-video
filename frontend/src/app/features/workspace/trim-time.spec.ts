import { clampTrim, formatTrimTime, parseTrimTime } from './trim-time';

describe('trim time', () => {
  it('parses minutes, hours and plain seconds', () => {
    expect(parseTrimTime('1:05.5')).toBe(65.5);
    expect(parseTrimTime('0:01:05,5')).toBe(65.5);
    expect(parseTrimTime(' 12 ')).toBe(12);
    expect(parseTrimTime('abc')).toBeNull();
    expect(parseTrimTime('1:-2')).toBeNull();
  });

  it('formats seconds with tenths', () => {
    expect(formatTrimTime(65.54)).toBe('1:05.5');
    expect(formatTrimTime(0)).toBe('0:00.0');
    expect(formatTrimTime(3725)).toBe('1:02:05.0');
  });

  it('keeps the range inside the video and at least half a second long', () => {
    expect(clampTrim(-3, 99, 10)).toEqual({ start: 0, end: 10 });
    expect(clampTrim(9.9, 9.9, 10)).toEqual({ start: 9.5, end: 10 });
    expect(clampTrim(4, 2, 10)).toEqual({ start: 4, end: 4.5 });
  });
});
