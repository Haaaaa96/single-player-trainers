#pragma once

/* Config is per Hookshot user directory, outside the game's save slots.
 * Changes are published in memory even if the disk write fails. */
static SRWLOCK hk_prefs_lock = SRWLOCK_INIT;
static INIT_ONCE hk_prefs_once = INIT_ONCE_STATIC_INIT;
static HkTrainerPrefs hk_prefs;
static char hk_prefs_file[4096];

static BOOL CALLBACK hk_load_prefs(PINIT_ONCE once, PVOID parameter, PVOID *context) {
    if (!hos_user_dir || !*hos_user_dir) return FALSE;
    const int n = snprintf(hk_prefs_file, sizeof hk_prefs_file, "%s\\HookshotTrainer.ini", hos_user_dir);
    if (n < 0 || n >= sizeof hk_prefs_file - 40) {
        hk_prefs_file[0] = 0;
        return TRUE;
    }
    FILE *file = fopen(hk_prefs_file, "rb");
    if (!file) return TRUE;
    char line[80];
    if (fgets(line, sizeof line, file) &&
        (!strcmp(line, "[HookshotTrainer/1]\n") || !strcmp(line, "[HookshotTrainer/1]\r\n"))) {
        while (fgets(line, sizeof line, file)) {
            line[strcspn(line, "\r\n")] = 0;
            if (!strcmp(line, "keep_health=1")) hk_prefs.flags |= HK_PREF_HEALTH;
            else if (!strcmp(line, "keep_ammo=1")) hk_prefs.flags |= HK_PREF_AMMO;
            else if (!strcmp(line, "keep_magic=1")) hk_prefs.flags |= HK_PREF_MAGIC;
            else if (!strcmp(line, "forest_navigation=1")) hk_prefs.flags |= HK_PREF_NAVIGATION;
            else if (!strcmp(line, "flight=1")) hk_prefs.flags |= HK_PREF_FLIGHT;
            else if (!strncmp(line, "forest_destination=", 19) &&
                     line[19] >= '0' && line[19] <= '4' && !line[20])
                hk_prefs.forest_destination = line[19]-'0';
        }
    }
    fclose(file);
    return TRUE;
}

static HkTrainerPrefs hk_prefs_get(void) {
    InitOnceExecuteOnce(&hk_prefs_once, hk_load_prefs, NULL, NULL);
    AcquireSRWLockShared(&hk_prefs_lock);
    const HkTrainerPrefs value = hk_prefs;
    ReleaseSRWLockShared(&hk_prefs_lock);
    return value;
}

static int hk_save_prefs(HkTrainerPrefs prefs) {
    if (!hk_prefs_file[0]) return 0;
    char temp[4096], text[180];
    snprintf(temp, sizeof temp, "%s.%lu.tmp", hk_prefs_file, (unsigned long)GetCurrentProcessId());
    const int n = snprintf(text, sizeof text,
        "[HookshotTrainer/1]\nkeep_health=%d\nkeep_ammo=%d\nkeep_magic=%d\nforest_navigation=%d\nflight=%d\nforest_destination=%d\n",
        !!(prefs.flags & HK_PREF_HEALTH), !!(prefs.flags & HK_PREF_AMMO), !!(prefs.flags & HK_PREF_MAGIC),
        !!(prefs.flags & HK_PREF_NAVIGATION), !!(prefs.flags & HK_PREF_FLIGHT), prefs.forest_destination);
    HANDLE file = CreateFileA(temp, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return 0;
    DWORD bytes = 0;
    int ok = WriteFile(file, text, (DWORD)n, &bytes, NULL) && bytes == (DWORD)n && FlushFileBuffers(file);
    CloseHandle(file);
    if (ok) ok = MoveFileExA(temp, hk_prefs_file, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH);
    if (!ok) DeleteFileA(temp);
    return ok;
}

static int hk_prefs_set(unsigned mask, unsigned flags, int forest_destination) {
    if (!InitOnceExecuteOnce(&hk_prefs_once, hk_load_prefs, NULL, NULL)) return 0;
    // Serialize writers without holding the snapshot lock during disk IO.
    static SRWLOCK writer = SRWLOCK_INIT;
    AcquireSRWLockExclusive(&writer);
    AcquireSRWLockExclusive(&hk_prefs_lock);
    mask &= HK_PREF_ALL;
    const unsigned next = (hk_prefs.flags & ~mask) | (flags & mask);
    if ((hk_prefs.flags ^ next) & HK_PREF_AMMO) ++hk_prefs.ammo_epoch;
    hk_prefs.flags = next;
    if (forest_destination >= 0 && forest_destination <= 4) hk_prefs.forest_destination = forest_destination;
    const HkTrainerPrefs prefs = hk_prefs;
    ReleaseSRWLockExclusive(&hk_prefs_lock);
    const int saved = hk_save_prefs(prefs);
    ReleaseSRWLockExclusive(&writer);
    return saved;
}
