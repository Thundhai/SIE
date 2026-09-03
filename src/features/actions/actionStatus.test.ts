import { describe, expect, it } from 'vitest';
import type { ActionStatus } from '../../types/actions';
import {
  ACTION_TERMINAL_STATUSES,
  actionStatusLabel,
  actionStatusTone,
  actionTypeLabel,
  isAllowedActionTransition,
  suggestedNextStatuses,
  toPriorityLevel,
} from './actionStatus';

describe('actionStatus', () => {
  it('gives every ActionStatus a tone and a readable label', () => {
    const statuses: ActionStatus[] = ['OPEN', 'IN_PROGRESS', 'BLOCKED', 'COMPLETED', 'CANCELLED'];
    for (const status of statuses) {
      expect(actionStatusTone(status)).toBeTruthy();
      expect(actionStatusLabel(status)).toBeTruthy();
    }
    expect(actionStatusLabel('IN_PROGRESS')).toBe('In progress');
    expect(actionStatusTone('COMPLETED')).toBe('success');
  });

  it('maps every ActionPriority onto PriorityBadge\'s lowercase PriorityLevel', () => {
    expect(toPriorityLevel('LOW')).toBe('low');
    expect(toPriorityLevel('CRITICAL')).toBe('critical');
  });

  it('gives every ActionType a readable label', () => {
    expect(actionTypeLabel('FOLLOW_UP')).toBe('Follow-up');
    expect(actionTypeLabel('CONTROL_IMPROVEMENT')).toBe('Control improvement');
  });

  it('mirrors the backend transition matrix exactly (app/models/safety_action_enums.py)', () => {
    expect(suggestedNextStatuses('OPEN')).toEqual(['IN_PROGRESS', 'BLOCKED', 'COMPLETED', 'CANCELLED']);
    expect(suggestedNextStatuses('IN_PROGRESS')).toEqual(['BLOCKED', 'COMPLETED', 'CANCELLED']);
    expect(suggestedNextStatuses('BLOCKED')).toEqual(['IN_PROGRESS', 'COMPLETED', 'CANCELLED']);
    expect(suggestedNextStatuses('COMPLETED')).toEqual([]);
    expect(suggestedNextStatuses('CANCELLED')).toEqual([]);
  });

  it('treats COMPLETED and CANCELLED as terminal, nothing else', () => {
    expect(ACTION_TERMINAL_STATUSES).toEqual(['COMPLETED', 'CANCELLED']);
  });

  it('isAllowedActionTransition() agrees with the transition table both ways', () => {
    expect(isAllowedActionTransition('OPEN', 'IN_PROGRESS')).toBe(true);
    expect(isAllowedActionTransition('OPEN', 'OPEN')).toBe(false);
    expect(isAllowedActionTransition('COMPLETED', 'OPEN')).toBe(false);
    expect(isAllowedActionTransition('CANCELLED', 'IN_PROGRESS')).toBe(false);
  });
});
