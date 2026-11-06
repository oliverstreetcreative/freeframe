'use client'

import * as React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { User, Bell, Shield, Palette } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'

interface SettingsNavItem {
  href: string
  label: string
  icon: React.ElementType
  adminOnly?: boolean
}

const settingsNavItems: SettingsNavItem[] = [
  { href: '/settings/profile', label: 'Profile', icon: User },
  { href: '/settings/appearance', label: 'Appearance', icon: Palette },
  { href: '/settings/notifications', label: 'Notifications', icon: Bell },
  { href: '/settings/admin', label: 'Admin', icon: Shield, adminOnly: true },
]

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const pathname = usePathname()
  const { user, isSuperAdmin } = useAuthStore()

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col md:flex-row">
      {/* Settings Sidebar */}
      <aside className="w-full border-b border-border bg-bg-secondary shrink-0 md:w-56 md:border-b-0 md:border-r">
        <div className="hidden p-4 border-b border-border md:block">
          <h2 className="text-sm font-semibold text-text-primary">Settings</h2>
          <p className="text-xs text-text-tertiary mt-0.5">
            {user?.name ?? 'User'}
          </p>
        </div>

        <nav className="flex flex-wrap gap-1 p-2 md:block md:space-y-0.5">
          {settingsNavItems.map((item) => {
            // Hide admin-only items from non-admins
            if (item.adminOnly && !isSuperAdmin) return null

            const isActive = pathname === item.href || pathname?.startsWith(item.href + '/')
            const Icon = item.icon

            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  'flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors',
                  isActive
                    ? 'bg-bg-hover text-text-primary font-medium'
                    : 'text-text-secondary hover:bg-bg-hover/70 hover:text-text-primary',
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span>{item.label}</span>
              </Link>
            )
          })}
        </nav>
      </aside>

      {/* Settings Content */}
      <main className="min-h-0 min-w-0 flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  )
}
