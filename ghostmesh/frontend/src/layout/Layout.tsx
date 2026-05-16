import { ReactNode } from 'react';
import { Sidebar } from './Sidebar';
import { MobileNav } from './MobileNav';
import { TopBar } from './TopBar';

interface Props { children: ReactNode }

export function Layout({ children }: Props) {
  return (
    <div style={{ background: 'var(--gm-bg-base)', minHeight: '100vh' }}>
      {/* Desktop sidebar */}
      <div className="hidden md:block">
        <Sidebar />
      </div>
      {/* Mobile top bar */}
      <div className="md:hidden">
        <TopBar />
      </div>
      {/* Main content */}
      <main className="md:ml-[220px] pt-[52px] md:pt-0 pb-[64px] md:pb-0 px-4 md:px-6 py-4 md:py-6 max-w-full overflow-x-hidden">
        {children}
      </main>
      {/* Mobile bottom nav */}
      <div className="md:hidden">
        <MobileNav />
      </div>
    </div>
  );
}
