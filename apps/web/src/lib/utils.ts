import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatNumber(value: number, decimals = 2): string {
  if (Math.abs(value) >= 1e6) {
    return (value / 1e6).toFixed(decimals) + 'M';
  }
  if (Math.abs(value) >= 1e3) {
    return (value / 1e3).toFixed(decimals) + 'K';
  }
  return value.toFixed(decimals);
}

export function formatPercentage(value: number, decimals = 1): string {
  return (value * 100).toFixed(decimals) + '%';
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) {
    return `${seconds.toFixed(0)}s`;
  }
  if (seconds < 3600) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}m ${secs}s`;
  }
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${mins}m`;
}

export function getGradeColor(level: string): string {
  switch (level) {
    case 'excellent':
      return 'text-green-600 bg-green-100';
    case 'very_good':
      return 'text-blue-600 bg-blue-100';
    case 'good':
      return 'text-cyan-600 bg-cyan-100';
    case 'acceptable':
      return 'text-yellow-600 bg-yellow-100';
    case 'unacceptable':
      return 'text-red-600 bg-red-100';
    default:
      return 'text-gray-600 bg-gray-100';
  }
}

export function getStatusColor(status: string): string {
  switch (status) {
    case 'running':
      return 'text-blue-600';
    case 'completed':
      return 'text-green-600';
    case 'failed':
      return 'text-red-600';
    case 'awaiting_input':
      return 'text-amber-600';
    default:
      return 'text-gray-600';
  }
}

export function getFidelityBadge(fidelity: string): string {
  switch (fidelity) {
    case 'high':
      return 'badge-success';
    case 'mid':
      return 'badge-info';
    case 'cheap':
      return 'badge-warning';
    default:
      return 'badge';
  }
}

export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength - 3) + '...';
}

export function generateId(): string {
  return Math.random().toString(36).substring(2, 15);
}
