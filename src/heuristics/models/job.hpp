#pragma once


class Job{
    public:
        int id;
        int processing_slots;
        int release_date_slot;
        int resource_id;

        Job(int id, int processing_slots, int release_date_slot, int resource_id)
            : id(id), processing_slots(processing_slots), release_date_slot(release_date_slot), resource_id(resource_id) {}
};
