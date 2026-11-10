#pragma once
#include <stdint.h>
typedef struct {
    const char *actor, *name, *category, *restriction;
    uint32_t stock, capacity;
    int price, cells, maximum;
} TrainerItem;
typedef struct {
    uint64_t generation;
    int ready, pending, keep_health, health, max_health, rupees, wallet;
    char message[160];
} TrainerStatus;
enum { TRAINER_HEAL=1, TRAINER_KEEP, TRAINER_RUPEES, TRAINER_ITEM, TRAINER_AMMO };
extern const TrainerItem trainer_items[];
extern const int trainer_item_count;
TrainerStatus trainer_status(void);
void trainer_request(uint64_t generation, int action, int item, int amount);
