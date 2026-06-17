import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { TrendingUp, TrendingDown, LucideIcon, Thermometer, Droplets, Wind, AlertTriangle } from 'lucide-react';
import { Status, SensorReading } from '../types';
import { cn } from '../lib/utils';

interface MetricCardProps {
  reading: SensorReading;
  icon: LucideIcon;
}

const statusColors: Record<Status, string> = {
  good: 'bg-emerald-500',
  warning: 'bg-amber-500',
  critical: 'bg-red-500',
  active: 'bg-blue-500',
};

const statusBorders: Record<Status, string> = {
  good: 'border-emerald-500/20',
  warning: 'border-amber-500/20',
  critical: 'border-red-500/50',
  active: 'border-blue-500/20',
};

const statusShadows: Record<Status, string> = {
  good: '',
  warning: '',
  critical: 'animate-critical',
  active: '',
};

export const MetricCard: React.FC<MetricCardProps> = ({ reading, icon: Icon }) => {
  return (
    <motion.div
      layout
      className={cn(
        "relative overflow-hidden bg-white rounded-lg p-5 border shadow-sm",
        statusBorders[reading.status],
        statusShadows[reading.status]
      )}
    >
      {/* Top accent line */}
      <div className={cn("absolute top-0 left-0 right-0 h-1", statusColors[reading.status])} />

      <div className="flex justify-between items-start mb-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            {reading.name}
          </p>
        </div>
        <Icon className={cn("w-5 h-5", reading.status === 'good' ? 'text-slate-300' : 'text-slate-500')} />
      </div>

      <div className="flex items-baseline gap-2 mb-2">
        <AnimatePresence mode="popLayout">
          <motion.span
            key={reading.value}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="text-4xl md:text-5xl font-bold tabular-nums text-slate-900"
          >
            {reading.value.toFixed(1)}
          </motion.span>
        </AnimatePresence>
        <span className="text-lg text-slate-400 font-medium">{reading.unit}</span>
      </div>

      <div className="flex items-center gap-2">
        <div className={cn(
          "flex items-center gap-1 text-xs font-bold px-1.5 py-0.5 rounded",
          reading.trend >= 0 ? "text-emerald-700 bg-emerald-50" : "text-amber-700 bg-amber-50"
        )}>
          {reading.trend >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
          <span>{Math.abs(reading.trend).toFixed(1)}%</span>
        </div>
        <span className="text-[10px] text-slate-400 uppercase tracking-tight font-medium">vs last hour</span>
      </div>

      {reading.status === 'critical' && (
        <div className="absolute bottom-2 right-2">
          <AlertTriangle className="w-4 h-4 text-red-500 animate-pulse" />
        </div>
      )}
    </motion.div>
  );
};
