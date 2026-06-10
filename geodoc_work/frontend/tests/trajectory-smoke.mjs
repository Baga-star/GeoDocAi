import { existsSync, readFileSync } from 'node:fs';

const requiredFiles = [
  'src/features/trajectory/TrajectoryWorkspace.tsx',
  'src/features/trajectory/TrajectoryNavigator.tsx',
  'src/features/trajectory/PlanView.tsx',
  'src/features/trajectory/ProfileView.tsx',
  'src/features/trajectory/ThreeDView.tsx',
  'src/features/trajectory/ExportReportButton.tsx',
];
for (const file of requiredFiles) {
  if (!existsSync(new URL(`../${file}`, import.meta.url))) throw new Error(`Missing ${file}`);
}
const main = readFileSync(new URL('../src/main.tsx', import.meta.url), 'utf8');
if (!main.includes('TrajectoryModeSwitch') || !main.includes('TrajectoryWorkspace')) {
  throw new Error('Trajectory mode is not wired into main.tsx');
}
console.log('trajectory frontend smoke: ok');
