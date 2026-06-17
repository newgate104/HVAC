export type Status = 'good' | 'warning' | 'critical' | 'active';

export interface SensorReading {
  id: string;
  name: string;
  value: number;
  unit: string;
  status: Status;
  trend: number; // percentage change
  icon: string;
}

export interface ChartDataPoint {
  time: string;
  temp: number | null;
  outdoorTemp: number | null;
  co2: number | null;
  pm25: number | null;
  power: number | null;
  energy: number | null;
  power_base: number | null;
  energy_base: number | null;
  power_ac: number | null;
  power_fan: number | null;
}

export interface ZoneManagerInfo {
  currentPolicy: 'working_hours' | 'night_eco' | 'eco_standby' | 'manual';
  overrideActive: boolean;
  remainingOverride: number;
  scheduledPolicy: 'working_hours' | 'night_eco' | 'eco_standby';
  aiRecommendation: string;
}

export interface TelemetryResponse {
  latest: {
    temperature: number | null;
    outdoor_temperature: number | null;
    humidity: number | null;
    co2: number | null;
    dust: number | null;
    time: string | null;
    power: number | null;
    energy: number | null;
    power_base: number | null;
    energy_base: number | null;
    power_ac: number | null;
    power_fan: number | null;
  };
  history: ChartDataPoint[];
  controlState: RemoteControlState | null;
  zoneManager: ZoneManagerInfo;
}

export interface HVACState {
  power: boolean;
  mode: 'auto' | 'cool' | 'heat' | 'off';
  targetTemp: number;
  fanSpeed: 'auto' | 'on' | 'off';
  co2Max: number;
  humidityMax: number;
}

export interface RemoteControlPayload {
  device_id: string;
  power: boolean;
  temp: number;
  operationMode: HVACState['mode'];
  fanPower: HVACState['fanSpeed'];
  co2Max: number;
  humidityMax: number;
  clientId: string;
  requestedAt: string;
}

export interface RemoteControlState extends RemoteControlPayload {
  time: string;
  lastModifiedAt: string;
  lastModifiedBy: string;
}

export interface RemoteControlResponse {
  ok: boolean;
  topic: string;
  command: RemoteControlState;
}
