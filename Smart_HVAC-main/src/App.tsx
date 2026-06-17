import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { 
  Thermometer, 
  Droplets, 
  Wind, 
  Activity, 
  Maximize2, 
  Bell, 
  User, 
  History,
  AlertTriangle,
  CloudRain,
  CloudSun,
  MapPin
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import mainLogo from '../img/main_logo_2.png';
import { MetricCard } from './components/MetricCard';
import { RealTimeChart } from './components/RealTimeChart';
import { ControlPanel } from './components/ControlPanel';
import { SensorReading, ChartDataPoint, HVACState, Status, TelemetryResponse, RemoteControlPayload, RemoteControlResponse, RemoteControlState, ZoneManagerInfo } from './types';
import { cn } from './lib/utils';

// Helper to determine status based on thresholds
const getStatus = (id: string, value: number): Status => {
  if (id === 'temp') {
    if (value > 26 || value < 18) return 'warning';
    return 'good';
  }
  if (id === 'humidity') {
    if (value > 60 || value < 30) return 'warning';
    return 'good';
  }
  if (id === 'co2') {
    if (value > 1000) return 'critical';
    if (value > 800) return 'warning';
    return 'good';
  }
  if (id === 'pm25') {
    if (value > 35) return 'critical';
    if (value > 12) return 'warning';
    return 'good';
  }
  return 'good';
};

interface HanoiWeather {
  temperature: number;
  apparentTemperature: number;
  humidity: number;
  windSpeed: number;
  minTemp: number;
  maxTemp: number;
  precipitationProbability: number;
  weatherCode: number;
}

type ControlField = keyof HVACState;

interface PendingControl {
  commandId: number;
  previousState: HVACState;
  desiredState: HVACState;
  fields: ControlField[];
}

interface ToastMessage {
  id: number;
  type: 'error' | 'info';
  message: string;
}

const CONTROL_FIELDS: ControlField[] = ['power', 'mode', 'targetTemp', 'fanSpeed'];

const getOrCreateClientId = () => {
  const key = 'smart-hvac-client-id';
  const existing = window.localStorage.getItem(key);
  if (existing) return existing;

  const next = window.crypto?.randomUUID?.() ?? `client-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  window.localStorage.setItem(key, next);
  return next;
};

const remoteToHVACState = (controlState: RemoteControlState): HVACState => ({
  power: controlState.power,
  mode: controlState.operationMode as any,
  targetTemp: controlState.temp,
  fanSpeed: controlState.fanPower as any,
  co2Max: controlState.co2Max ?? 800,
  humidityMax: controlState.humidityMax ?? 60,
});

const getControlRevision = (controlState: RemoteControlState) =>
  controlState.lastModifiedAt || controlState.time;

const formatClientLabel = (id: string) => `Người dùng ${id === 'unknown' ? 'khác' : id.slice(-6)}`;

const getWeatherLabel = (code: number) => {
  if (code === 0) return 'Clear';
  if ([1, 2, 3].includes(code)) return 'Partly Cloudy';
  if ([45, 48].includes(code)) return 'Foggy';
  if ([51, 53, 55, 56, 57].includes(code)) return 'Drizzle';
  if ([61, 63, 65, 66, 67, 80, 81, 82].includes(code)) return 'Rain';
  if ([95, 96, 99].includes(code)) return 'Thunderstorm';
  return 'Cloudy';
};

export default function App() {
  // --- STATE ---
  const [readings, setReadings] = useState<SensorReading[]>([
    { id: 'temp', name: 'Ambient Temp', value: 22.4, unit: '°C', status: 'good', trend: 1.2, icon: 'Thermometer' },
    { id: 'humidity', name: 'Relative Humidity', value: 45.1, unit: '%', status: 'good', trend: -0.5, icon: 'Droplets' },
    { id: 'co2', name: 'CO2 Levels', value: 420.0, unit: 'ppm', status: 'good', trend: 2.1, icon: 'Wind' },
    { id: 'pm25', name: 'Particulates (PM2.5)', value: 8.5, unit: 'µg/m³', status: 'good', trend: 0.8, icon: 'Activity' },
  ]);

  const [history, setHistory] = useState<ChartDataPoint[]>([]);
  const [hvacState, setHvacState] = useState<HVACState>({
    power: true,
    mode: 'auto',
    targetTemp: 25.0,
    fanSpeed: 'auto',
    co2Max: 800,
    humidityMax: 60,
  });
  const [pendingControl, setPendingControl] = useState<PendingControl | null>(null);
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const [hanoiWeather, setHanoiWeather] = useState<HanoiWeather | null>(null);
  const [isControlStateReady, setIsControlStateReady] = useState(false);
  const clientId = useMemo(getOrCreateClientId, []);
  const commandSequenceRef = useRef(0);
  const hvacStateRef = useRef(hvacState);
  const pendingControlRef = useRef<PendingControl | null>(null);
  const controlReadyRef = useRef(false);
  const lastControlRevisionRef = useRef<string | null>(null);
  const [zoneManager, setZoneManager] = useState<ZoneManagerInfo | null>(null);
  const [latestPower, setLatestPower] = useState<number>(0);
  const [latestEnergy, setLatestEnergy] = useState<number>(0);
  const [latestPowerAc, setLatestPowerAc] = useState<number>(0);
  const [latestPowerFan, setLatestPowerFan] = useState<number>(0);
  const [latestPowerBase, setLatestPowerBase] = useState<number>(0);
  const [latestEnergyBase, setLatestEnergyBase] = useState<number>(0);

  useEffect(() => {
    hvacStateRef.current = hvacState;
  }, [hvacState]);

  useEffect(() => {
    pendingControlRef.current = pendingControl;
  }, [pendingControl]);

  useEffect(() => {
    controlReadyRef.current = isControlStateReady;
  }, [isControlStateReady]);

  useEffect(() => {
    if (!toast) return;
    const timeout = window.setTimeout(() => setToast(null), 3500);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  const showToast = useCallback((type: ToastMessage['type'], message: string) => {
    setToast({ id: Date.now(), type, message });
  }, []);

  const postRemoteControl = useCallback(async (nextState: HVACState, requestedAt: string) => {
    const payload: RemoteControlPayload = {
      device_id: 'hvac-01',
      power: nextState.power,
      temp: nextState.targetTemp,
      operationMode: nextState.mode,
      fanPower: nextState.fanSpeed,
      co2Max: nextState.co2Max,
      humidityMax: nextState.humidityMax,
      clientId,
      requestedAt,
    };
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 6000);

    try {
      const response = await fetch('/api/remote-control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`Remote control request failed: ${response.status}`);
      }

      const result: RemoteControlResponse = await response.json();
      return remoteToHVACState(result.command);
    } catch (error) {
      console.error(error);
      throw error;
    } finally {
      window.clearTimeout(timeout);
    }
  }, [clientId]);

  const sendRemoteControl = useCallback(async (getNextState: (state: HVACState) => HVACState) => {
    const previousState = hvacStateRef.current;
    const baseState = pendingControlRef.current?.desiredState ?? previousState;
    const desiredState = getNextState(baseState);
    const fields = CONTROL_FIELDS.filter(field => previousState[field] !== desiredState[field]);
    const commandId = commandSequenceRef.current + 1;
    commandSequenceRef.current = commandId;

    if (fields.length === 0) {
      pendingControlRef.current = null;
      setPendingControl(null);
      return;
    }

    const nextPendingControl = {
      commandId,
      previousState,
      desiredState,
      fields,
    };
    pendingControlRef.current = nextPendingControl;
    setPendingControl(nextPendingControl);

    try {
      const officialState = await postRemoteControl(desiredState, new Date().toISOString());
      if (pendingControlRef.current?.commandId !== commandId) return;

      setHvacState(officialState);
      pendingControlRef.current = null;
      setPendingControl(null);
    } catch {
      if (pendingControlRef.current?.commandId !== commandId) return;

      setHvacState(previousState);
      pendingControlRef.current = null;
      setPendingControl(null);
      showToast('error', 'Kết nối tới thiết bị thất bại');
    }
  }, [postRemoteControl, showToast]);

  // --- DATABASE TELEMETRY ---
  useEffect(() => {
    const updateReading = (reading: SensorReading, nextValue: number | null): SensorReading => {
      if (nextValue === null || Number.isNaN(nextValue)) {
        return reading;
      }

      return {
        ...reading,
        value: nextValue,
        status: getStatus(reading.id, nextValue),
        trend: reading.value === 0 ? 0 : ((nextValue - reading.value) / reading.value) * 100,
      };
    };

    const fetchTelemetry = async () => {
      try {
        const response = await fetch('/api/telemetry');
        if (!response.ok) {
          throw new Error(`Telemetry request failed: ${response.status}`);
        }

        const telemetry: TelemetryResponse = await response.json();
        setHistory(telemetry.history);
        if (telemetry.latest) {
          setLatestPower(telemetry.latest.power ?? 0);
          setLatestEnergy(telemetry.latest.energy ?? 0);
          setLatestPowerAc(telemetry.latest.power_ac ?? 0);
          setLatestPowerFan(telemetry.latest.power_fan ?? 0);
          setLatestPowerBase(telemetry.latest.power_base ?? 0);
          setLatestEnergyBase(telemetry.latest.energy_base ?? 0);
        }
        if (telemetry.zoneManager) {
          setZoneManager(telemetry.zoneManager);
        }
        if (telemetry.controlState) {
          const incomingState = remoteToHVACState(telemetry.controlState);
          const incomingRevision = getControlRevision(telemetry.controlState);
          const isNewRevision = lastControlRevisionRef.current !== incomingRevision;
          const isExternalChange = telemetry.controlState.lastModifiedBy !== clientId;
          const wasReady = controlReadyRef.current;

          setHvacState(prevState => {
            const pending = pendingControlRef.current;
            if (!pending) return incomingState;

            return CONTROL_FIELDS.reduce<HVACState>((nextState, field) => {
              if (pending.fields.includes(field)) {
                return nextState;
              }

              return {
                ...nextState,
                [field]: incomingState[field],
              };
            }, prevState);
          });

          if (isNewRevision && wasReady && isExternalChange) {
            showToast('info', `${formatClientLabel(telemetry.controlState.lastModifiedBy)} vừa đổi nhiệt độ`);
          }

          lastControlRevisionRef.current = incomingRevision;
        }
        if (!controlReadyRef.current) {
          controlReadyRef.current = true;
          setIsControlStateReady(true);
        }
        setReadings(prev => prev.map(reading => {
          if (reading.id === 'temp') return updateReading(reading, telemetry.latest.temperature);
          if (reading.id === 'humidity') return updateReading(reading, telemetry.latest.humidity);
          if (reading.id === 'co2') return updateReading(reading, telemetry.latest.co2);
          if (reading.id === 'pm25') return updateReading(reading, telemetry.latest.dust);
          return reading;
        }));
      } catch (error) {
        console.error(error);
      }
    };

    fetchTelemetry();
    const interval = window.setInterval(fetchTelemetry, 2000);

    return () => window.clearInterval(interval);
  }, [clientId, showToast]);

  // --- WEATHER ---
  useEffect(() => {
    const fetchHanoiWeather = async () => {
      try {
        const params = new URLSearchParams({
          latitude: '21.0245',
          longitude: '105.8412',
          current: 'temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m',
          daily: 'temperature_2m_max,temperature_2m_min,precipitation_probability_max',
          timezone: 'Asia/Bangkok',
          forecast_days: '1',
        });
        const response = await fetch(`https://api.open-meteo.com/v1/forecast?${params.toString()}`);
        if (!response.ok) {
          throw new Error(`Weather request failed: ${response.status}`);
        }

        const weather = await response.json();
        setHanoiWeather({
          temperature: weather.current.temperature_2m,
          apparentTemperature: weather.current.apparent_temperature,
          humidity: weather.current.relative_humidity_2m,
          windSpeed: weather.current.wind_speed_10m,
          weatherCode: weather.current.weather_code,
          minTemp: weather.daily.temperature_2m_min[0],
          maxTemp: weather.daily.temperature_2m_max[0],
          precipitationProbability: weather.daily.precipitation_probability_max[0],
        });
      } catch (error) {
        console.error(error);
      }
    };

    fetchHanoiWeather();
    const interval = window.setInterval(fetchHanoiWeather, 2 * 60 * 60 * 1000);

    return () => window.clearInterval(interval);
  }, []);

  // Derived stats
  const activeAlerts = useMemo(() => readings.filter(r => r.status !== 'good').length, [readings]);
  const displayHvacState = pendingControl?.desiredState ?? hvacState;
  const pendingFields = useMemo(() => {
    return pendingControl?.fields.reduce<Partial<Record<ControlField, boolean>>>((fields, field) => {
      fields[field] = true;
      return fields;
    }, {}) ?? {};
  }, [pendingControl]);

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900 overflow-x-clip selection:bg-blue-500/20">
      {/* --- TOP BAR --- */}
      <header className="fixed top-0 left-0 right-0 h-16 bg-white/80 backdrop-blur-md border-b border-slate-200 z-50 px-4 md:px-8 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <img src={mainLogo} alt="HVAC Sentinel Logo" className="h-10 object-contain" />
        </div>

        <div className="flex items-center gap-4">
          <div className="hidden md:flex items-center gap-6 mr-6 border-r border-slate-200 pr-6">
            <div className="flex flex-col items-end">
              <span className="text-[10px] text-slate-400 uppercase font-bold tracking-widest">Uptime</span>
              <span className="text-xs font-mono text-slate-600">12d 04h 22m</span>
            </div>
          </div>

          <div className="relative">
            <Bell className="w-5 h-5 text-slate-400 hover:text-slate-600 cursor-pointer transition-colors" />
            {activeAlerts > 0 && (
              <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-red-500 rounded-full border-2 border-slate-900" />
            )}
          </div>
          <div className="w-8 h-8 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center overflow-hidden">
             <User className="w-5 h-5 text-slate-400" />
          </div>
        </div>
      </header>

      {/* --- MAIN CONTENT --- */}
      <main className="pt-24 pb-8 px-4 md:px-8 max-w-[1600px] mx-auto">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          
          {/* Dashboard Left Section: Metrics & Charts */}
          <div className="lg:col-span-8 space-y-6">
            
            {/* Header info */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h2 className="text-2xl font-bold tracking-tight">System Overview</h2>
                <p className="text-slate-400 text-sm">Zone: Main Server Hall A-42 • Floor 12</p>
              </div>
              <div className="flex gap-2">
                <button className="flex items-center gap-2 px-3 py-1.5 bg-white hover:bg-slate-50 rounded text-xs font-semibold text-slate-600 transition-colors border border-slate-200">
                  <History className="w-3.5 h-3.5" />
                  Logs
                </button>
                <button className="flex items-center gap-2 px-3 py-1.5 bg-white hover:bg-slate-50 rounded text-xs font-semibold text-slate-600 transition-colors border border-slate-200">
                  <Maximize2 className="w-3.5 h-3.5" />
                  Fullscreen
                </button>
              </div>
            </div>

            {/* Metric Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
              <MetricCard reading={readings[0]} icon={Thermometer} />
              <MetricCard reading={readings[1]} icon={Droplets} />
              <MetricCard reading={readings[2]} icon={Wind} />
              <MetricCard reading={readings[3]} icon={Activity} />
            </div>

            {/* Main Visualizations */}
            <div className="grid grid-cols-1 gap-6">
              <RealTimeChart data={history} />
            </div>

            {/* Secondary Intel */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
               <div className="bg-white rounded-lg p-5 border border-slate-200 shadow-sm flex flex-col justify-between min-h-[250px]">
                  <div>
                    <div className="flex items-center justify-between mb-4">
                      <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">HIỆU QUẢ TỐI ƯU CỦA AI</h4>
                      <span className="flex items-center gap-1 text-[9px] font-bold px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 animate-pulse">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                        AI COORD ACTIVE
                      </span>
                    </div>

                    <div className="space-y-3">
                      {/* Big Savings Metric */}
                      <div className="flex items-center gap-4 bg-emerald-50/50 p-3 rounded-lg border border-emerald-100">
                        <div className="w-10 h-10 rounded-full bg-emerald-500/20 flex items-center justify-center text-emerald-600 font-extrabold text-sm animate-pulse">
                          🍃
                        </div>
                        <div>
                          <p className="text-[8px] text-emerald-600 font-extrabold uppercase tracking-tight">AI GIÚP TIẾT KIỆM ĐIỆN NĂNG</p>
                          <p className="text-xl font-black font-mono text-emerald-700 leading-none mt-1">
                            {latestEnergyBase > latestEnergy 
                              ? (((latestEnergyBase - latestEnergy) / latestEnergyBase) * 100).toFixed(1)
                              : '0.0'}%
                          </p>
                          <p className="text-[8px] text-slate-500 font-bold mt-1">
                            Lượng điện giảm: {Math.max(0, latestEnergyBase - latestEnergy).toFixed(3)} kWh
                          </p>
                        </div>
                      </div>

                      {/* Savings Breakdown */}
                      <div className="grid grid-cols-2 gap-3 text-xs font-semibold pt-1">
                        <div className="border-r border-slate-100 pr-2">
                          <p className="text-[8px] text-slate-400 font-extrabold uppercase">CHI PHÍ ĐÃ GIẢM</p>
                          <p className="text-sm font-black text-emerald-600 mt-0.5">
                            - {Math.max(0, (latestEnergyBase - latestEnergy) * 2500).toLocaleString('vi-VN', { maximumFractionDigits: 0 })} VNĐ
                          </p>
                        </div>
                        <div className="pl-2">
                          <p className="text-[8px] text-slate-400 font-extrabold uppercase">GIẢM PHÁT THẢI CO2</p>
                          <p className="text-sm font-black text-slate-700 mt-0.5">
                            - {Math.max(0, (latestEnergyBase - latestEnergy) * 0.5).toFixed(3)} kg
                          </p>
                        </div>
                      </div>

                      {/* Current active policy */}
                      <div className="flex justify-between items-center border-t border-slate-100 pt-2 text-xs">
                        <span className="text-slate-500 font-medium">Chế độ vận hành của AI</span>
                        <span className="text-[9px] font-bold uppercase text-slate-800 bg-slate-100 px-2 py-0.5 rounded">
                          {zoneManager?.currentPolicy === 'working_hours' && '💼 Giờ làm việc'}
                          {zoneManager?.currentPolicy === 'night_eco' && '🌙 Ngủ đêm ECO'}
                          {zoneManager?.currentPolicy === 'eco_standby' && '🍃 Chờ tiết kiệm'}
                          {zoneManager?.currentPolicy === 'manual' && '👤 Thủ công'}
                        </span>
                      </div>

                      {/* AI recommendation */}
                      <div className="p-2.5 rounded bg-slate-50 border border-slate-100 text-[10px] text-slate-500 leading-relaxed font-medium">
                        <span className="font-extrabold text-slate-400 block mb-0.5 uppercase text-[8px] tracking-tight">AI RECOMMENDATION:</span>
                        {zoneManager?.aiRecommendation || 'Đang phân tích hoạt động phòng...'}
                      </div>
                    </div>
                  </div>
               </div>
               <div className="bg-white rounded-xl p-5 border border-slate-200 shadow-sm flex flex-col justify-between min-h-[280px]">
                  <div className="space-y-4">
                    <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center justify-between">
                      <span>ĐIỆN NĂNG TIÊU THỤ (AI SIMULATOR)</span>
                      <span className="flex items-center gap-1 text-[8px] font-extrabold px-1.5 py-0.5 rounded bg-blue-50 text-blue-600 border border-blue-100">
                        <span className="w-1 h-1 rounded-full bg-blue-500 animate-pulse" />
                        Đang giám sát
                      </span>
                    </h4>
                    
                    {/* Real-time Load & Consumption */}
                    <div className="grid grid-cols-2 gap-4 bg-slate-50 p-3 rounded-lg border border-slate-100">
                      <div>
                        <p className="text-[8px] text-slate-400 uppercase font-extrabold tracking-tight">TỔNG TIÊU THỤ (AI)</p>
                        <p className="text-2xl font-black font-mono text-slate-900 tracking-tight leading-none mt-1">
                          {latestEnergy.toFixed(3)}
                          <span className="text-xs text-slate-400 ml-1 font-bold">kWh</span>
                        </p>
                        <p className="text-[8px] text-slate-500 font-semibold tracking-tighter leading-none mt-1">
                          Tạm tính: {(latestEnergy * 2500).toLocaleString('vi-VN', { maximumFractionDigits: 0 })} VNĐ
                        </p>
                      </div>
                      <div>
                        <p className="text-[8px] text-slate-400 uppercase font-extrabold tracking-tight">CÔNG SUẤT TỨC THÌ</p>
                        <p className="text-2xl font-black font-mono text-blue-600 tracking-tight leading-none mt-1">
                          {latestPower >= 1000 ? (latestPower / 1000).toFixed(2) : latestPower.toFixed(0)}
                          <span className="text-xs text-slate-400 ml-1 font-bold">{latestPower >= 1000 ? 'kW' : 'W'}</span>
                        </p>
                        <span className={`inline-flex items-center gap-0.5 text-[8px] font-extrabold px-1.5 py-0.5 rounded mt-1.5 ${
                          latestPower < 50 
                            ? 'bg-emerald-50 text-emerald-600 border border-emerald-100'
                            : latestPower < 500
                            ? 'bg-sky-50 text-sky-600 border border-sky-100'
                            : 'bg-orange-50 text-orange-600 border border-orange-100'
                        }`}>
                          {latestPower < 50 ? 'Chờ/Tiết kiệm' : latestPower < 500 ? 'Tải Trung bình' : 'Tải Cao'}
                        </span>
                      </div>
                    </div>

                    {/* Breakdown section */}
                    <div className="space-y-1.5">
                      <span className="text-[8px] text-slate-400 font-extrabold uppercase block">Phân rã công suất (AI Breakdown)</span>
                      <div className="grid grid-cols-3 gap-2">
                        <div className="bg-slate-50/50 border border-slate-100 rounded p-2 text-center">
                          <p className="text-[8px] text-slate-400 font-bold uppercase tracking-tight">ĐIỀU HÒA (AC)</p>
                          <p className="text-xs font-black font-mono text-slate-700 mt-0.5">{latestPowerAc.toFixed(0)} W</p>
                        </div>
                        <div className="bg-slate-50/50 border border-slate-100 rounded p-2 text-center">
                          <p className="text-[8px] text-slate-400 font-bold uppercase tracking-tight">QUẠT GIÓ (FAN)</p>
                          <p className="text-xs font-black font-mono text-slate-700 mt-0.5">{latestPowerFan.toFixed(0)} W</p>
                        </div>
                        <div className="bg-slate-50/50 border border-slate-100 rounded p-2 text-center">
                          <p className="text-[8px] text-slate-400 font-bold uppercase tracking-tight">HỆ THỐNG (STBY)</p>
                          <p className="text-xs font-black font-mono text-slate-700 mt-0.5">5 W</p>
                        </div>
                      </div>
                    </div>

                    {/* Baseline Comparison section */}
                    <div className="border-t border-slate-100 pt-3 space-y-2">
                      <div className="flex justify-between items-center">
                        <span className="text-[8px] text-slate-400 font-extrabold uppercase">So sánh hiệu quả với Baseline</span>
                        {latestEnergyBase > 0 && latestEnergyBase > latestEnergy ? (
                          <span className="inline-flex items-center gap-0.5 text-[8.5px] font-black text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-100 animate-pulse">
                            🍃 AI tiết kiệm: {(((latestEnergyBase - latestEnergy) / latestEnergyBase) * 100).toFixed(1)}%
                          </span>
                        ) : (
                          <span className="text-[8px] text-slate-400 font-bold italic">Đang phân tích...</span>
                        )}
                      </div>
                      
                      <div className="grid grid-cols-2 gap-4 text-xs font-semibold">
                        <div className="border-r border-slate-100 pr-2">
                          <p className="text-[8px] text-emerald-600 font-extrabold uppercase">HỆ THỐNG AI TỐI ƯU</p>
                          <p className="text-sm font-black font-mono text-slate-800 mt-0.5">{latestEnergy.toFixed(3)} kWh</p>
                          <p className="text-[7.5px] text-slate-400 font-bold">~{(latestEnergy * 2500).toLocaleString('vi-VN', { maximumFractionDigits: 0 })} VNĐ</p>
                        </div>
                        <div className="pl-2">
                          <p className="text-[8px] text-slate-400 font-extrabold uppercase">BASELINE (CHƯA TỐI ƯU)</p>
                          <p className="text-sm font-black font-mono text-slate-400 mt-0.5">{latestEnergyBase.toFixed(3)} kWh</p>
                          <p className="text-[7.5px] text-slate-400 font-bold">~{(latestEnergyBase * 2500).toLocaleString('vi-VN', { maximumFractionDigits: 0 })} VNĐ</p>
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  {/* Sparkline chart at the very bottom */}
                  <div className="flex items-center justify-between pt-3 border-t border-slate-100 mt-3">
                    <span className="text-[8px] text-slate-400 font-extrabold uppercase">Biểu đồ tải (7 điểm gần nhất)</span>
                    <div className="w-32 h-8 flex items-end gap-0.5">
                      {(() => {
                        const lastPowerPoints = history.slice(-7);
                        const maxPower = Math.max(...lastPowerPoints.map(p => p.power ?? 0), 100);
                        return lastPowerPoints.map((pt, i) => {
                          const power = pt.power ?? 0;
                          const heightPercent = maxPower > 0 ? (power / maxPower) * 100 : 10;
                          return (
                            <div 
                              key={i} 
                              className={`flex-1 rounded-t-sm transition-all duration-500 ${
                                power < 50 ? 'bg-emerald-400/60' : power < 500 ? 'bg-sky-400/80' : 'bg-blue-500'
                              }`}
                              style={{ height: `${Math.max(10, heightPercent)}%` }}
                              title={`AI: ${power.toFixed(0)}W | Baseline: ${(pt.power_base ?? 0).toFixed(0)}W`}
                            />
                          );
                        });
                      })()}
                    </div>
                  </div>
               </div>
            </div>
          </div>

          {/* Dashbaord Right Section: Controls & Status */}
          <div className="lg:col-span-4 space-y-6">
            
            {isControlStateReady ? (
              <ControlPanel
                state={displayHvacState}
                pendingFields={pendingFields}
                onControlChange={sendRemoteControl}
              />
            ) : (
              <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-xl h-full min-h-[560px] flex flex-col">
                <div className="flex items-center justify-between mb-6">
                  <div>
                    <h3 className="text-sm font-bold uppercase tracking-widest text-slate-400">AC Unit 01</h3>
                    <div className="flex items-center gap-2 mt-1">
                      <div className="w-1.5 h-1.5 rounded-full bg-slate-300 animate-pulse" />
                      <span className="text-[10px] font-bold text-slate-400 uppercase">Loading State</span>
                    </div>
                  </div>
                  <div className="w-11 h-11 rounded-full bg-slate-100 animate-pulse" />
                </div>
                <div className="flex-1 flex flex-col items-center justify-center gap-8">
                  <div className="w-full aspect-square max-w-[200px] rounded-full border-8 border-slate-50 bg-slate-50 animate-pulse" />
                  <div className="w-full space-y-3">
                    <div className="h-3 w-32 mx-auto bg-slate-100 rounded animate-pulse" />
                    <div className="grid grid-cols-3 gap-3">
                      {[0, 1, 2].map((item) => (
                        <div key={item} className="h-20 rounded-2xl bg-slate-50 border-2 border-slate-50 animate-pulse" />
                      ))}
                    </div>
                  </div>
                  <div className="w-full space-y-3">
                    <div className="h-3 w-24 bg-slate-100 rounded animate-pulse" />
                    <div className="h-12 rounded-xl bg-slate-50 border border-slate-100 animate-pulse" />
                  </div>
                </div>
              </div>
            )}

            {/* Weather */}
            <div className="bg-white rounded-lg p-5 border border-slate-200 shadow-sm">
               <div className="flex items-center justify-between mb-4">
                  <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Weather</h4>
                  <div className="flex items-center gap-1 text-[10px] text-slate-400 font-medium uppercase">
                    <MapPin className="w-3 h-3" />
                    Today
                  </div>
               </div>
                {hanoiWeather ? (
                  <div className="space-y-4">
                    {[
                      { item: 'Current Temperature', status: `${hanoiWeather.temperature.toFixed(1)}°C`, color: 'text-blue-600' },
                      { item: 'Condition', status: getWeatherLabel(hanoiWeather.weatherCode), color: 'text-sky-600' },
                      { item: 'Feels Like', status: `${hanoiWeather.apparentTemperature.toFixed(1)}°C`, color: 'text-slate-600' },
                    ].map((step) => (
                      <div key={step.item} className="flex justify-between items-center border-b border-slate-100 pb-2">
                         <span className="text-xs text-slate-600 font-medium">{step.item}</span>
                         <span className={cn("text-[10px] font-bold uppercase", step.color)}>{step.status}</span>
                      </div>
                    ))}
                    <div className="grid grid-cols-2 gap-x-4 gap-y-3">
                      {[
                        { label: 'Humidity', value: `${hanoiWeather.humidity}%`, icon: Droplets },
                        { label: 'Wind', value: `${hanoiWeather.windSpeed.toFixed(1)} km/h`, icon: Wind },
                        { label: 'High / Low', value: `${hanoiWeather.maxTemp.toFixed(1)} / ${hanoiWeather.minTemp.toFixed(1)}°C`, icon: Thermometer },
                        { label: 'Rain Chance', value: `${hanoiWeather.precipitationProbability}%`, icon: CloudRain },
                      ].map((item) => (
                        <div key={item.label} className="flex items-center justify-between gap-2 border-b border-slate-100 pb-2">
                          <div className="flex items-center gap-1.5 text-slate-400 mb-1">
                            <item.icon className="w-3 h-3" />
                            <span className="text-[9px] font-bold uppercase">{item.label}</span>
                          </div>
                          <p className="text-xs font-mono font-bold text-slate-700">{item.value}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="h-28 flex items-center justify-center">
                    <span className="text-xs text-slate-400 font-medium">Loading weather...</span>
                  </div>
                )}
            </div>

            {/* Notification Center */}
            <div className="bg-white rounded-lg p-6 border border-slate-200 shadow-sm">
               <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-4">System Alerts</h4>
               <div className="space-y-4">
                  <AnimatePresence>
                    {activeAlerts > 0 ? (
                      readings.filter(r => r.status !== 'good').map((r) => (
                        <motion.div 
                          key={r.id}
                          initial={{ opacity: 0, x: 20 }}
                          animate={{ opacity: 1, x: 0 }}
                          exit={{ opacity: 0, x: -20 }}
                          className={cn(
                            "p-3 rounded border flex items-start gap-3",
                            r.status === 'critical' ? "bg-red-50 border-red-100" : "bg-amber-50 border-amber-100"
                          )}
                        >
                           <AlertTriangle className={cn("w-4 h-4 shrink-0", r.status === 'critical' ? "text-red-500" : "text-amber-500")} />
                           <div className="space-y-1">
                              <p className="text-[11px] font-bold text-slate-800 uppercase tracking-tight">High {r.name} Detected</p>
                              <p className="text-[10px] text-slate-500">Current value {r.value.toFixed(1)}{r.unit} exceeds threshold.</p>
                           </div>
                        </motion.div>
                      ))
                    ) : (
                      <div className="text-center py-6">
                        <p className="text-[10px] text-slate-400 uppercase font-bold">All systems nominal</p>
                      </div>
                    )}
                  </AnimatePresence>
               </div>
            </div>

          </div>
        </div>
      </main>
      <AnimatePresence>
        {toast && (
          <motion.div
            key={toast.id}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 16 }}
            className={cn(
              "fixed bottom-6 right-6 z-[60] max-w-sm rounded-lg border px-4 py-3 shadow-xl flex items-start gap-3",
              toast.type === 'error'
                ? "bg-red-50 border-red-200 text-red-700"
                : "bg-blue-50 border-blue-200 text-blue-700"
            )}
          >
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <p className="text-xs font-bold">{toast.message}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
