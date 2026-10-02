-- Stage 6 migration: separate OTP purposes for teacher registration/login.
-- Run once in Supabase SQL Editor.
alter table public.teacher_otps add column if not exists purpose varchar(30);
update public.teacher_otps set purpose = 'teacher_login' where purpose is null;
alter table public.teacher_otps alter column purpose set not null;
create index if not exists idx_teacher_otps_teacher_purpose on public.teacher_otps(teacher_id,purpose);
