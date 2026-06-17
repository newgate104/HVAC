import React from 'react';
import { Power, Wind, Sun, Snowflake, Fan, Thermometer, LoaderCircle, Droplets } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { HVACState } from '../types';
import { cn } from '../lib/utils';

interface ControlPanelProps {
  state: HVACState;
  pendingFields: Partial<Record<keyof HVACState, boolean>>;
  onControlChange: (getNextState: (state: HVACState) => HVACState) => void;
}

export const ControlPanel: React.FC<ControlPanelProps> = ({ state, pendingFields, onControlChange }) => {
  const updateControl = (getNextState: (state: HVACState) => HVACState) => {
    onControlChange(getNextState);
  };

  const togglePower = () => updateControl(prev => ({ ...prev, power: !prev.power }));
  
  const setMode = (mode: HVACState['mode']) => updateControl(prev => ({ ...prev, mode }));
  
  const setFanSpeed = (fanSpeed: HVACState['fanSpeed']) => updateControl(prev => ({ ...prev, fanSpeed }));

  const modeColors: Record<string, string> = {
    auto: 'text-purple-500 bg-purple-50 border-purple-200',
    cool: 'text-blue-500 bg-blue-50 border-blue-200',
    heat: 'text-orange-500 bg-orange-50 border-orange-200',
    off: 'text-slate-500 bg-slate-50 border-slate-200',
  };

  const modeGlows: Record<string, string> = {
    auto: 'shadow-[0_0_20px_rgba(168,85,247,0.15)]',
    cool: 'shadow-[0_0_20px_rgba(59,130,246,0.15)]',
    heat: 'shadow-[0_0_20px_rgba(249,115,22,0.15)]',
    off: 'shadow-none',
  };

  const isPending = Object.values(pendingFields).some(Boolean);
  const isAutoMode = state.mode === 'auto';

  return (
    <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-xl h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-sm font-bold uppercase tracking-widest text-slate-400">AC UNIT 01</h3>
          <div className="flex items-center gap-2">
            <div className={cn("w-1.5 h-1.5 rounded-full", state.power ? "bg-emerald-500 animate-pulse" : "bg-slate-300")} />
            <span className="text-[10px] font-bold text-slate-500 uppercase">
              {isPending ? 'Syncing Command' : state.power ? 'System Ready' : 'Standby'}
            </span>
          </div>
        </div>
        <button
          onClick={togglePower}
          className={cn(
            "p-3 rounded-full transition-all duration-500 ring-4",
            state.power 
              ? "bg-emerald-500 ring-emerald-100 text-white shadow-lg" 
              : "bg-slate-100 ring-slate-50 text-slate-300"
          )}
        >
          <Power className="w-5 h-5" />
        </button>
      </div>

      <div className={cn("flex-1 space-y-8 transition-all duration-700", !state.power && "opacity-20 grayscale pointer-events-none")}>
        
        {/* Visual Temperature Controller */}
        <div className="relative flex flex-col items-center">
          <div className={cn(
            "w-full aspect-square max-w-[200px] rounded-full border-8 border-slate-50 bg-white flex flex-col items-center justify-center transition-all duration-500",
            pendingFields.targetTemp && "opacity-60",
            state.power && modeGlows[state.mode],
            isAutoMode && "opacity-80"
          )}>
            <div className="text-slate-400 mb-1 flex items-center gap-1">
              <Thermometer className="w-3 h-3" />
              <span className="text-[10px] font-bold uppercase tracking-tighter">
                {isAutoMode ? 'Target (AI)' : 'Manual Override'}
              </span>
            </div>
            
            <div className="relative">
              <AnimatePresence mode="wait">
                <motion.div
                  key={state.targetTemp}
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 1.1 }}
                  className="text-6xl font-bold font-mono text-slate-900 tabular-nums leading-none"
                >
                  {state.targetTemp.toFixed(1)}
                </motion.div>
              </AnimatePresence>
              {pendingFields.targetTemp && (
                <LoaderCircle className="absolute -right-6 top-1 w-5 h-5 text-blue-500 animate-spin" />
              )}
            </div>
            
            <span className="text-xl font-bold text-slate-400 mt-1">°C</span>
          </div>
        </div>

        {/* Safety Thresholds Displays */}
        <div className="grid grid-cols-2 gap-3">
          {/* CO2 Threshold Card */}
          <div className="bg-slate-50 border border-slate-100 rounded-xl p-3 flex flex-col items-center justify-between text-center min-h-[110px]">
            <div className="text-emerald-500 flex items-center gap-1">
              <Wind className="w-3.5 h-3.5" />
              <span className="text-[9px] font-extrabold uppercase tracking-wider">Ngưỡng CO2</span>
            </div>
            
            <div className="flex flex-col items-center justify-center my-1.5">
              <p className="text-lg font-extrabold font-mono text-slate-800 leading-none tabular-nums">
                {state.co2Max ?? 800} <span className="text-xs text-slate-400 font-bold">ppm</span>
              </p>
              <span className="text-[8px] text-emerald-600 font-bold mt-1 bg-emerald-50 px-1.5 py-0.5 rounded-full border border-emerald-100 flex items-center gap-0.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                AI Tự động
              </span>
            </div>
            <span className="text-[7.5px] text-slate-400 font-bold uppercase tracking-tighter leading-none">Bật quạt nếu vượt quá</span>
          </div>

          {/* Humidity Threshold Card */}
          <div className="bg-slate-50 border border-slate-100 rounded-xl p-3 flex flex-col items-center justify-between text-center min-h-[110px]">
            <div className="text-blue-500 flex items-center gap-1">
              <Droplets className="w-3.5 h-3.5" />
              <span className="text-[9px] font-extrabold uppercase tracking-wider">Ngưỡng Độ Ẩm</span>
            </div>
            
            <div className="flex flex-col items-center justify-center my-1.5">
              <p className="text-lg font-extrabold font-mono text-slate-800 leading-none tabular-nums">
                {state.humidityMax ?? 60}.0<span className="text-xs text-slate-400 font-bold">%</span>
              </p>
              <span className="text-[8px] text-blue-600 font-bold mt-1 bg-blue-50 px-1.5 py-0.5 rounded-full border border-blue-100 flex items-center gap-0.5">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                AI Tự động
              </span>
            </div>
            <span className="text-[7.5px] text-slate-400 font-bold uppercase tracking-tighter leading-none">Bật quạt nếu vượt quá</span>
          </div>
        </div>

        {/* HVAC Operation Mode Selection */}
        <div className="space-y-3">
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block text-center">HVAC Mode</span>
          
          <div className="flex gap-2 p-1 bg-slate-50 rounded-xl border border-slate-200">
            <button
              onClick={() => setMode('auto')}
              className={cn(
                "flex-1 py-2 rounded-lg text-[10px] font-bold uppercase transition-all",
                isAutoMode 
                  ? "bg-white text-purple-600 shadow-md ring-1 ring-slate-200" 
                  : "text-slate-400 hover:text-slate-600"
              )}
            >
              Auto
            </button>
            <button
              onClick={() => {
                if (isAutoMode) {
                  setMode('cool'); // Mặc định chọn cooling khi chuyển sang thủ công
                }
              }}
              className={cn(
                "flex-1 py-2 rounded-lg text-[10px] font-bold uppercase transition-all",
                !isAutoMode 
                  ? "bg-white text-slate-900 shadow-md ring-1 ring-slate-200" 
                  : "text-slate-400 hover:text-slate-600"
              )}
            >
              Manual
            </button>
          </div>

          {/* Sub-modes for manual control */}
          <AnimatePresence>
            {!isAutoMode && (
              <motion.div 
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="overflow-hidden"
              >
                <div className="grid grid-cols-3 gap-2 pt-1">
                  {[
                    { id: 'cool', icon: Snowflake, label: 'Làm lạnh', activeClass: 'text-blue-500 bg-blue-50 border-blue-200 shadow-[0_0_15px_rgba(59,130,246,0.1)]' },
                    { id: 'heat', icon: Sun, label: 'Làm nóng', activeClass: 'text-orange-500 bg-orange-50 border-orange-200 shadow-[0_0_15px_rgba(249,115,22,0.1)]' },
                    { id: 'off', icon: Power, label: 'Tắt HVAC', activeClass: 'text-slate-500 bg-slate-50 border-slate-200' },
                  ].map((m) => {
                    const isActive = state.mode === m.id;
                    return (
                      <button
                        key={m.id}
                        onClick={() => setMode(m.id as HVACState['mode'])}
                        className={cn(
                          "flex flex-col items-center gap-1.5 py-2.5 px-1 rounded-xl border transition-all text-center",
                          isActive 
                            ? m.activeClass 
                            : "bg-white border-slate-100 text-slate-400 hover:border-slate-200"
                        )}
                      >
                        <m.icon className="w-4 h-4 animate-none" />
                        <span className="text-[8px] uppercase font-extrabold tracking-tight">{m.label}</span>
                      </button>
                    );
                  })}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Fan Speed - Visual Slider feel */}
        <div className="space-y-3">
          <div className="flex justify-between items-center px-1">
             <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Ventilating Fan</span>
             <Fan 
               className={cn("w-3.5 h-3.5 text-slate-300", state.power && state.fanSpeed !== 'off' && "animate-spin")} 
               style={{ animationDuration: state.fanSpeed === 'auto' ? '2.5s' : '1.2s' }} 
             />
          </div>
          
          <div className="flex gap-2 p-1 bg-slate-50 rounded-xl border border-slate-200">
            <button
              onClick={() => setFanSpeed('auto')}
              className={cn(
                "flex-1 py-2 rounded-lg text-[10px] font-bold uppercase transition-all",
                state.fanSpeed === 'auto' 
                  ? "bg-white text-emerald-600 shadow-md ring-1 ring-slate-200" 
                  : "text-slate-400 hover:text-slate-600"
              )}
            >
              Auto
            </button>
            <button
              onClick={() => {
                if (state.fanSpeed === 'auto') {
                  setFanSpeed('on');
                }
              }}
              className={cn(
                "flex-1 py-2 rounded-lg text-[10px] font-bold uppercase transition-all",
                state.fanSpeed !== 'auto' 
                  ? "bg-white text-slate-900 shadow-md ring-1 ring-slate-200" 
                  : "text-slate-400 hover:text-slate-600"
              )}
            >
              Manual
            </button>
          </div>

          <AnimatePresence>
            {state.fanSpeed !== 'auto' && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="overflow-hidden"
              >
                <div className="flex gap-2 pt-1">
                  {[
                    { id: 'on', label: 'Bật quạt (ON)', activeClass: 'bg-emerald-500 text-white shadow-md border-emerald-500' },
                    { id: 'off', label: 'Tắt quạt (OFF)', activeClass: 'bg-slate-500 text-white shadow-md border-slate-500' }
                  ].map((item) => {
                    const isActive = state.fanSpeed === item.id;
                    return (
                      <button
                        key={item.id}
                        onClick={() => setFanSpeed(item.id as HVACState['fanSpeed'])}
                        className={cn(
                          "flex-1 py-2 rounded-xl border text-[9px] font-bold uppercase transition-all text-center",
                          isActive 
                            ? item.activeClass 
                            : "bg-white border-slate-100 text-slate-400 hover:border-slate-200"
                        )}
                      >
                        {item.label}
                      </button>
                    );
                  })}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
};
