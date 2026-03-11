# Changelog

All notable changes to Hospital AI Assistant will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [6.1.0] — 2026-03-11 — Phase 6.1: Mobile Doctor Prescription Assist

### Added
- 🎤 **Voice-to-text assist** for all major prescription input fields:
  - Chief Complaint, Diagnosis, Symptoms, Clinical Notes
  - Diet Advice and Special Instructions
  - Uses browser Web Speech API (en-IN / hi-IN / te-IN)
  - Graceful fallback when speech recognition unsupported
  - States: idle / listening / processing / failed / unsupported
- 📋 **Save Draft** — saves prescription locally (localStorage) so doctor can resume after switch
- ✈️ **Manual Telegram Notify button** on prescription action bar
- 💬 **WhatsApp Coming Soon button** (disabled, shows badge — no API required now)
- 🕐 **Self Check-In / Check-Out** for any authenticated staff (doctors, nurses, reception):
  - New nav section "My Attendance" in doctor dashboard
  - Live clock display
  - Status badge: checked-in / checked-out / not tracked
  - No admin login required — uses own session
  - Sends Telegram alert on check-in
- 🔔 **Toast notifications** — success/error/info for all major actions
- 📱 **Mobile sticky action bar** — prescription buttons stick to bottom on small screens
- 🏗️ **Enhanced mobile styles** for medicine/lab rows (stacked on ≤768px)

### API Changes
- `POST /api/staff/self-checkin` — any authenticated staff can record own check-in
- `POST /api/staff/self-checkout` — any authenticated staff can record own check-out
- `GET /api/staff/self-status` — returns today's attendance records for current user
- Telegram notification via `notify_prescription_saved()` auto-fires on `POST /api/doctor/prescription/create`
- Telegram notification via `notify_staff_checkin()` auto-fires on staff self check-in

### Telegram
- Added `notify_prescription_saved(patient, phone, doctor, rx_id)` function
- Added `notify_staff_checkin(staff_name, role, action)` function
- Added `_send_message()` convenience alias

### Migration
- `migration_v5_phase61_attendance.sql` — adds `username` + `role` columns to `attendance` table; safe to re-run

### Security
- Self check-in/out endpoints require valid session (any role) — no admin escalation
- WhatsApp button is disabled/non-functional until API provider configured — no backend dependency

### Known Limitations
- Voice input uses browser Web Speech API — Safari/iOS may have limited support; manual typing always fallback
- WhatsApp sending not implemented — prepared structure only
- Draft saved in localStorage — not server-side; clears on browser data clear

---

## [1.0.0] - 2026-02-05

### Added
- ✨ Multilingual voice interface (English, Hindi, Telugu)
- 🎤 Real-time speech recognition and text-to-speech
- 📅 Complete appointment booking system
- 👨‍⚕️ Doctor scheduling and availability management
- 📝 Patient registration with data validation
- 👨‍💼 Admin dashboard with real-time monitoring
- 📊 Google Sheets API integration
- 🤖 OpenAI GPT-powered chatbot with memory
- 🔔 n8n workflow automation support
- 📱 Telegram notifications integration
- 📡 RESTful API for external integration
- 🌐 Responsive mobile-first design
- 🔐 Secure authentication system
- 🧪 Comprehensive test coverage
- 📖 Complete documentation

### Features
- Voice-based appointment booking in 3 languages
- Real-time conversation memory and context
- Multi-turn dialogue for natural interaction
- Appointment confirmation and SMS alerts
- Hospital staff notifications via Telegram
- Data persistence in Google Sheets
- ngrok-based public URL access
- Progressive Web App capabilities
- Docker deployment support

### Security
- HTTPS/TLS encryption
- Session timeout management
- Input validation and sanitization
- Rate limiting on API endpoints
- Credential management with .env files

---

## [Upcoming]

### Planned for v1.1
- [ ] Database migration (PostgreSQL/MySQL)
- [ ] Advanced analytics dashboard
- [ ] Multi-server load balancing
- [ ] Video consultation integration
- [ ] Prescription management
- [ ] Electronic health records

### Planned for v2.0
- [ ] Mobile app (React Native)
- [ ] Multi-hospital support
- [ ] AI-powered diagnosis assistance
- [ ] Advanced appointment algorithms
- [ ] Payment integration
- [ ] Telemedicine capabilities

---

## How to Report Issues

Found a bug? Have a feature request?
1. Check [existing issues](https://github.com/shashankpasikanti91-blip/Hospital-AI-Assistant/issues)
2. [Create a new issue](https://github.com/shashankpasikanti91-blip/Hospital-AI-Assistant/issues/new)
3. Include:
   - Clear description
   - Steps to reproduce
   - Expected behavior
   - Environment details

---

## Versioning

We use [Semantic Versioning](https://semver.org/):
- **MAJOR**: Breaking changes
- **MINOR**: New features (backwards compatible)
- **PATCH**: Bug fixes

Format: `MAJOR.MINOR.PATCH`

---

## Release Schedule

- **Minor releases**: Monthly (feature updates)
- **Patch releases**: As needed (bug fixes)
- **Major releases**: Quarterly (breaking changes)

---

Generated on: 2026-02-05
