'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import { useTheme } from './ThemeProvider';

interface FloatingOrb {
  id: number;
  x: number;
  y: number;
  size: number;
  speedX: number;
  speedY: number;
  opacity: number;
  hue: number;
}

export function AnimatedBackground() {
  const { resolvedTheme } = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const mouseRef = useRef({ x: 0.5, y: 0.5, targetX: 0.5, targetY: 0.5 });
  const orbsRef = useRef<FloatingOrb[]>([]);
  const animationRef = useRef<number>();
  const [isReducedMotion, setIsReducedMotion] = useState(false);

  // Check for reduced motion preference
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    setIsReducedMotion(mediaQuery.matches);
    
    const handleChange = (e: MediaQueryListEvent) => setIsReducedMotion(e.matches);
    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, []);

  // Initialize floating orbs
  useEffect(() => {
    const orbCount = 5; // Minimal orbs for performance
    orbsRef.current = Array.from({ length: orbCount }, (_, i) => ({
      id: i,
      x: Math.random(),
      y: Math.random(),
      size: 200 + Math.random() * 300,
      speedX: (Math.random() - 0.5) * 0.0003,
      speedY: (Math.random() - 0.5) * 0.0003,
      opacity: 0.03 + Math.random() * 0.05,
      hue: resolvedTheme === 'dark' ? 220 + Math.random() * 40 : 200 + Math.random() * 40,
    }));
  }, [resolvedTheme]);

  // Smooth mouse tracking with throttling
  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (isReducedMotion) return;
    
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    
    // Normalize to 0-1 range
    mouseRef.current.targetX = e.clientX / rect.width;
    mouseRef.current.targetY = e.clientY / rect.height;
  }, [isReducedMotion]);

  // Animation loop with requestAnimationFrame
  useEffect(() => {
    if (isReducedMotion) return;

    let lastTime = 0;
    const targetFPS = 30; // Lower FPS for performance
    const frameInterval = 1000 / targetFPS;

    const animate = (currentTime: number) => {
      animationRef.current = requestAnimationFrame(animate);
      
      const deltaTime = currentTime - lastTime;
      if (deltaTime < frameInterval) return;
      lastTime = currentTime - (deltaTime % frameInterval);

      // Smooth mouse interpolation (easing)
      const easeFactor = 0.08;
      mouseRef.current.x += (mouseRef.current.targetX - mouseRef.current.x) * easeFactor;
      mouseRef.current.y += (mouseRef.current.targetY - mouseRef.current.y) * easeFactor;

      // Update orbs
      orbsRef.current.forEach((orb) => {
        // Natural floating movement
        orb.x += orb.speedX;
        orb.y += orb.speedY;

        // Add subtle mouse influence
        const mouseInfluence = 0.02;
        orb.x += (mouseRef.current.x - 0.5) * mouseInfluence * 0.1;
        orb.y += (mouseRef.current.y - 0.5) * mouseInfluence * 0.1;

        // Bounce at edges
        if (orb.x < -0.2 || orb.x > 1.2) orb.speedX *= -1;
        if (orb.y < -0.2 || orb.y > 1.2) orb.speedY *= -1;

        // Keep in bounds
        orb.x = Math.max(-0.3, Math.min(1.3, orb.x));
        orb.y = Math.max(-0.3, Math.min(1.3, orb.y));
      });

      // Update CSS custom properties for orb positions
      const container = containerRef.current;
      if (container) {
        orbsRef.current.forEach((orb, i) => {
          container.style.setProperty(`--orb-${i}-x`, `${orb.x * 100}%`);
          container.style.setProperty(`--orb-${i}-y`, `${orb.y * 100}%`);
        });
        
        // Mouse gradient position
        container.style.setProperty('--mouse-x', `${mouseRef.current.x * 100}%`);
        container.style.setProperty('--mouse-y', `${mouseRef.current.y * 100}%`);
      }
    };

    animationRef.current = requestAnimationFrame(animate);
    
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [isReducedMotion]);

  // Mouse move listener with passive for performance
  useEffect(() => {
    if (isReducedMotion) return;
    
    window.addEventListener('mousemove', handleMouseMove, { passive: true });
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, [handleMouseMove, isReducedMotion]);

  const isDark = resolvedTheme === 'dark';

  return (
    <div
      ref={containerRef}
      className="fixed inset-0 -z-10 overflow-hidden pointer-events-none"
      style={{
        '--mouse-x': '50%',
        '--mouse-y': '50%',
        '--orb-0-x': '20%',
        '--orb-0-y': '30%',
        '--orb-1-x': '70%',
        '--orb-1-y': '60%',
        '--orb-2-x': '40%',
        '--orb-2-y': '80%',
        '--orb-3-x': '80%',
        '--orb-3-y': '20%',
        '--orb-4-x': '10%',
        '--orb-4-y': '70%',
      } as React.CSSProperties}
    >
      {/* Base gradient that transitions with theme */}
      <div
        className={`
          absolute inset-0 transition-colors duration-700 ease-in-out
          ${isDark 
            ? 'bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950' 
            : 'bg-gradient-to-br from-slate-50 via-white to-blue-50'
          }
        `}
      />

      {/* Mouse-following gradient spotlight */}
      <div
        className={`
          absolute w-[600px] h-[600px] rounded-full blur-3xl
          transition-opacity duration-500
          ${isDark ? 'opacity-20' : 'opacity-30'}
        `}
        style={{
          left: 'var(--mouse-x)',
          top: 'var(--mouse-y)',
          transform: 'translate(-50%, -50%)',
          background: isDark
            ? 'radial-gradient(circle, rgba(59, 130, 246, 0.5) 0%, transparent 70%)'
            : 'radial-gradient(circle, rgba(59, 130, 246, 0.3) 0%, transparent 70%)',
          willChange: 'left, top',
        }}
      />

      {/* Floating orbs */}
      {[0, 1, 2, 3, 4].map((i) => (
        <div
          key={i}
          className={`
            absolute rounded-full blur-3xl
            transition-opacity duration-700
            ${isDark ? 'opacity-[0.07]' : 'opacity-[0.15]'}
          `}
          style={{
            width: `${200 + i * 80}px`,
            height: `${200 + i * 80}px`,
            left: `var(--orb-${i}-x)`,
            top: `var(--orb-${i}-y)`,
            transform: 'translate(-50%, -50%)',
            background: isDark
              ? `radial-gradient(circle, hsl(${220 + i * 15}, 70%, 50%) 0%, transparent 70%)`
              : `radial-gradient(circle, hsl(${200 + i * 20}, 80%, 60%) 0%, transparent 70%)`,
            willChange: 'left, top',
          }}
        />
      ))}

      {/* Grid pattern overlay */}
      <div
        className={`
          absolute inset-0 transition-opacity duration-700
          ${isDark ? 'opacity-[0.03]' : 'opacity-[0.02]'}
        `}
        style={{
          backgroundImage: `
            linear-gradient(${isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)'} 1px, transparent 1px),
            linear-gradient(90deg, ${isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)'} 1px, transparent 1px)
          `,
          backgroundSize: '50px 50px',
        }}
      />

      {/* Noise texture for depth */}
      <div
        className="absolute inset-0 opacity-[0.015]"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E")`,
        }}
      />
    </div>
  );
}
