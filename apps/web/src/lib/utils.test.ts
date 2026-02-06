import { describe, expect, it } from 'vitest';
import {
    cn,
    formatDuration,
    formatNumber,
    formatPercentage,
    generateId,
    getFidelityBadge,
    getGradeColor,
    getStatusColor,
    truncate,
} from './utils';

describe('cn', () => {
  it('merges class names', () => {
    expect(cn('foo', 'bar')).toBe('foo bar');
  });

  it('handles conditional classes', () => {
    expect(cn('base', true && 'included', false && 'excluded')).toBe('base included');
  });

  it('merges tailwind classes correctly', () => {
    expect(cn('px-2', 'px-4')).toBe('px-4');
  });
});

describe('formatNumber', () => {
  it('formats small numbers', () => {
    expect(formatNumber(123.456)).toBe('123.46');
    expect(formatNumber(0.123, 3)).toBe('0.123');
  });

  it('formats thousands with K suffix', () => {
    expect(formatNumber(1500)).toBe('1.50K');
    expect(formatNumber(12345)).toBe('12.35K');
  });

  it('formats millions with M suffix', () => {
    expect(formatNumber(1500000)).toBe('1.50M');
    expect(formatNumber(12345678)).toBe('12.35M');
  });

  it('respects decimal places', () => {
    expect(formatNumber(123.456789, 4)).toBe('123.4568');
    expect(formatNumber(1234, 0)).toBe('1K');
  });
});

describe('formatPercentage', () => {
  it('formats decimal as percentage', () => {
    expect(formatPercentage(0.5)).toBe('50.0%');
    expect(formatPercentage(0.123)).toBe('12.3%');
    expect(formatPercentage(1)).toBe('100.0%');
  });

  it('respects decimal places', () => {
    expect(formatPercentage(0.5555, 2)).toBe('55.55%');
    expect(formatPercentage(0.5, 0)).toBe('50%');
  });
});

describe('formatDuration', () => {
  it('formats seconds', () => {
    expect(formatDuration(30)).toBe('30s');
    expect(formatDuration(59)).toBe('59s');
  });

  it('formats minutes and seconds', () => {
    expect(formatDuration(90)).toBe('1m 30s');
    expect(formatDuration(125)).toBe('2m 5s');
  });

  it('formats hours and minutes', () => {
    expect(formatDuration(3700)).toBe('1h 1m');
    expect(formatDuration(7200)).toBe('2h 0m');
  });
});

describe('getGradeColor', () => {
  it('returns correct color for each level', () => {
    expect(getGradeColor('excellent')).toContain('green');
    expect(getGradeColor('very_good')).toContain('blue');
    expect(getGradeColor('good')).toContain('cyan');
    expect(getGradeColor('acceptable')).toContain('yellow');
    expect(getGradeColor('unacceptable')).toContain('red');
    expect(getGradeColor('unknown')).toContain('gray');
  });
});

describe('getStatusColor', () => {
  it('returns correct color for each status', () => {
    expect(getStatusColor('running')).toContain('blue');
    expect(getStatusColor('completed')).toContain('green');
    expect(getStatusColor('failed')).toContain('red');
    expect(getStatusColor('idle')).toContain('gray');
  });
});

describe('getFidelityBadge', () => {
  it('returns correct badge class for each fidelity', () => {
    expect(getFidelityBadge('high')).toBe('badge-success');
    expect(getFidelityBadge('mid')).toBe('badge-info');
    expect(getFidelityBadge('cheap')).toBe('badge-warning');
    expect(getFidelityBadge('unknown')).toBe('badge');
  });
});

describe('truncate', () => {
  it('does not truncate short strings', () => {
    expect(truncate('hello', 10)).toBe('hello');
  });

  it('truncates long strings with ellipsis', () => {
    expect(truncate('hello world', 8)).toBe('hello...');
  });

  it('handles exact length', () => {
    expect(truncate('hello', 5)).toBe('hello');
  });
});

describe('generateId', () => {
  it('generates unique IDs', () => {
    const id1 = generateId();
    const id2 = generateId();
    expect(id1).not.toBe(id2);
  });

  it('generates string IDs', () => {
    expect(typeof generateId()).toBe('string');
    expect(generateId().length).toBeGreaterThan(0);
  });
});
