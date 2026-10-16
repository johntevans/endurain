import { describe, expect, it } from 'vitest'

import {
  ACTIVITY_TYPE_LABEL_KEYS,
  activityTypeIsDistanceBased,
  activityTypeToGearType,
  presentActivityType,
} from '@/features/activities/utils/activityType'
import en from '@/i18n/locales/en/activities.json'

// Homelab fork: activity types the fork adds (ids from 1001, clear of upstream's).
describe('physical therapy activity type (1001)', () => {
  it('has a label that exists in the English catalog', () => {
    expect(ACTIVITY_TYPE_LABEL_KEYS[1001]).toBe('activities.types.physicalTherapy')
    // The i18n plugin compiles locale JSON to message ASTs, so check presence only.
    expect(en.types.physicalTherapy).toBeDefined()
    expect(presentActivityType(1001).labelKey).toBe('activities.types.physicalTherapy')
  })

  it('is a non-distance session with no gear', () => {
    expect(activityTypeIsDistanceBased(1001)).toBe(false)
    expect(activityTypeToGearType(1001)).toBeNull()
  })
})
