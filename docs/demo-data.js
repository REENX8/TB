// ============================================================
// TB Tracker — Demo Data (mock patients + doses)
// ============================================================

const TODAY = new Date();
TODAY.setHours(0, 0, 0, 0);

function addDays(d, n) {
  const r = new Date(d); r.setDate(r.getDate() + n); return r;
}
function fmtDate(d) {
  return d.toLocaleDateString('th-TH', {day:'2-digit', month:'2-digit', year:'numeric'});
}
function fmtYMD(d) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

const DRUG_IMAGES = {
  'INH 100mg':          'https://via.placeholder.com/72x72/a5d6a7/388e3c?text=INH',
  'Rifampicin 300mg':   'https://via.placeholder.com/72x72/ef9a9a/c62828?text=RIF',
  'Rifampicin 450mg':   'https://via.placeholder.com/72x72/ef9a9a/c62828?text=RIF',
  'PZA 500mg':          'https://via.placeholder.com/72x72/fff176/f9a825?text=PZA',
  'EMB 400mg':          'https://via.placeholder.com/72x72/90caf9/1565c0?text=EMB',
  'EMB 500mg':          'https://via.placeholder.com/72x72/90caf9/1565c0?text=EMB',
};

// ---------- Regimens ----------
const REG_65 = {'INH 100mg':3,'Rifampicin 300mg':2,'PZA 500mg':3,'EMB 500mg':2};
const REG_48 = {'INH 100mg':3,'Rifampicin 450mg':1,'PZA 500mg':2,'EMB 400mg':2};
const REG_72 = {'INH 100mg':3,'Rifampicin 300mg':2,'PZA 500mg':4,'EMB 400mg':3};
const REG_28 = {'INH 100mg':2,'Rifampicin 300mg':1,'PZA 500mg':1.5,'EMB 500mg':1};
const REG_MDR= {'Levofloxacin 500mg':2,'Ethionamide 250mg':3,'Cycloserine 250mg':2,'Pyridoxine 10mg':3};

// Generate dose history: adherence=fraction of past days taken
function genDoses(patient, totalDays, adherenceRate) {
  const doses = [];
  for (let i = 0; i < totalDays; i++) {
    const d = addDays(patient.start_date, i);
    const isPast = d < TODAY;
    const isToday = fmtYMD(d) === fmtYMD(TODAY);
    let taken = false, taken_time = null;
    if (isPast && Math.random() < adherenceRate) {
      taken = true;
      taken_time = new Date(d); taken_time.setHours(7 + Math.floor(Math.random()*3), Math.floor(Math.random()*60));
    }
    doses.push({ id: i+1, date: new Date(d), medications: patient.regimen, taken, taken_time, isToday, isPast });
  }
  return doses;
}

// Seed random with patient id so data is deterministic
function seededRandom(seed) {
  let x = Math.sin(seed) * 10000;
  return x - Math.floor(x);
}
function genDosesDet(patient, totalDays, adherenceRate) {
  const doses = [];
  for (let i = 0; i < totalDays; i++) {
    const d = addDays(patient.start_date, i);
    const isPast = d < TODAY;
    const isToday = fmtYMD(d) === fmtYMD(TODAY);
    let taken = false, taken_time = null;
    if (isPast && seededRandom(patient.id * 1000 + i) < adherenceRate) {
      taken = true;
      taken_time = new Date(d);
      taken_time.setHours(7 + Math.floor(seededRandom(patient.id * 999 + i) * 3),
                          Math.floor(seededRandom(patient.id * 777 + i) * 60));
    }
    doses.push({ id: i+1, date: new Date(d), medications: patient.regimen, taken, taken_time, isToday, isPast });
  }
  return doses;
}

const PATIENTS = [
  {
    id: 1, name: 'นายสมชาย ใจดี', hn: '12345', age: 42, tb_no: 'TB-001',
    weight: 65, tb_type: 'Pulmonary TB', outcome: '',
    phone: '0812345678', notes: 'แพ้ยาไม่มี, ติดตามปกติ',
    start_date: addDays(TODAY, -150), regimen: REG_65, total_days: 180,
    adherence: 0.88,
  },
  {
    id: 2, name: 'นางสาวสุดา มีสุข', hn: '23456', age: 29, tb_no: 'TB-002',
    weight: 48, tb_type: 'Pulmonary TB', outcome: '',
    phone: '0823456789', notes: '',
    start_date: addDays(TODAY, -90), regimen: REG_48, total_days: 180,
    adherence: 0.97,
  },
  {
    id: 3, name: 'นายประสิทธิ์ ศรีชัย', hn: '34567', age: 55, tb_no: 'TB-003',
    weight: 72, tb_type: 'Extrapulmonary TB', outcome: '',
    phone: '0834567890', notes: 'โรคเบาหวานร่วมด้วย ติดตามใกล้ชิด',
    start_date: addDays(TODAY, -120), regimen: REG_72, total_days: 180,
    adherence: 0.62,
  },
  {
    id: 4, name: 'เด็กชายณัฐ สมบูรณ์', hn: '45678', age: 9, tb_no: 'TB-004',
    weight: 28, tb_type: 'Pulmonary TB', outcome: '',
    phone: '0845678901', notes: 'ผู้ปกครอง: นางแดง สมบูรณ์',
    start_date: addDays(TODAY, -60), regimen: REG_28, total_days: 180,
    adherence: 0.93,
  },
  {
    id: 5, name: 'นางวาสนา เจริญ', hn: '56789', age: 38, tb_no: 'TB-005',
    weight: 55, tb_type: 'MDR-TB', outcome: 'transferred_out',
    phone: '0856789012', notes: 'ส่งต่อ รพ.กลาง',
    start_date: addDays(TODAY, -240), regimen: REG_MDR, total_days: 365,
    adherence: 0.75, archived: true,
  },
];

PATIENTS.forEach(p => { p.doses = genDosesDet(p, p.total_days, p.adherence); });

function getStats(patient) {
  const pastDoses = patient.doses.filter(d => d.isPast || d.isToday);
  const taken = pastDoses.filter(d => d.taken).length;
  const overdue = pastDoses.length - taken;
  const pct = pastDoses.length > 0 ? Math.round(taken / pastDoses.length * 1000) / 10 : 0;
  return { total_past: pastDoses.length, taken, overdue, total_all: patient.doses.length, adherence_pct: pct };
}

function getTodayDose(patient) {
  return patient.doses.find(d => fmtYMD(d.date) === fmtYMD(TODAY)) || null;
}

const OUTCOME_LABELS = {
  '': 'กำลังรักษา', cured: 'หาย (Cured)', completed: 'รักษาครบ (Completed)',
  failed: 'ไม่สำเร็จ (Failed)', defaulted: 'ขาดยา (Defaulted)',
  died: 'เสียชีวิต (Died)', transferred_out: 'ส่งต่อ (Transferred out)',
};
