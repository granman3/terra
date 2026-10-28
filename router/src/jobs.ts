// The AI jobs that arrive at Utah's site, one per replay hour, in this order (shared by server.ts, export-web.ts
// for the phone, and deck/utah_savings.ts). The mix is real, the individual jobs are not:
//   - shares of GPU-hours match Alibaba's 2026 production trace of 155,410 GPUs (cluster-trace-gpu-v2026, OSDI '26;
//     data/collected/jobs): online inference 53%, training 22%, offline (batch) inference 20%, dev notebooks 4%.
//     So 42% of the GPU-hours could wait and 57% can't.
//   - the training run's size is the median of the 100–1,000 GPU-hour bucket in Alibaba's PAI 2020 trace (204 GPU-h,
//     NSDI '22); the other sizes follow from the shares.
//   - can wait = 16 h for training and batch work (Terra's longest wait, 12 h, plus the 4 h run), 0 for anything a person
//     or a service is waiting on. That rule is Terra's, not the trace's.
export interface Job {
  name: string;
  label: string; // plain words, for the map and the phone
  deadlineHours: number; // 0 = must run now
  gpuHours: number;
}

export const JOBS: Job[] = [
  { name: "online-chat", label: "Chatbot answers", deadlineHours: 0, gpuHours: 245 },
  { name: "training-run", label: "AI model training", deadlineHours: 16, gpuHours: 204 },
  { name: "online-search", label: "Search and recommendations", deadlineHours: 0, gpuHours: 246 },
  { name: "batch-inference", label: "Overnight batch AI work", deadlineHours: 16, gpuHours: 185 },
  { name: "dev-notebook", label: "Developer notebook", deadlineHours: 0, gpuHours: 33 },
];

export const JOB_MIX_SOURCE = "Alibaba 2026 GPU trace (155,410 GPUs): 53% of GPU-hours live answers, 42% training and batch work";
