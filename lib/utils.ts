import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(date: string | Date): string {
  return new Date(date).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

export function formatNumber(num: number | null | undefined, decimals = 2): string {
  if (num == null) return 'N/A'
  return num.toFixed(decimals)
}

export function formatMillions(num: number | null | undefined): string {
  if (num == null) return 'N/A'
  const sign = num >= 0 ? '+' : ''
  return `${sign}$${num.toFixed(0)}M`
}
