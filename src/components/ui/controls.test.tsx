import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { Button } from './Button';
import { Input } from './Input';
import { SearchInput } from './SearchInput';
import { Select } from './Select';
import { Tabs } from './Tabs';

describe('Button', () => {
  it('is a real, keyboard-activatable button and calls onClick', async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Clear filters</Button>);
    const button = screen.getByRole('button', { name: 'Clear filters' });
    await userEvent.click(button);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('respects disabled and does not fire onClick', async () => {
    const onClick = vi.fn();
    render(
      <Button onClick={onClick} disabled>
        Save
      </Button>,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(onClick).not.toHaveBeenCalled();
  });
});

describe('Input', () => {
  it('renders a real, associated label (§18 accessible form labels)', () => {
    render(<Input label="Event title" />);
    expect(screen.getByLabelText('Event title')).toBeInTheDocument();
  });

  it('associates error text via aria-describedby and aria-invalid', () => {
    render(<Input label="Event title" errorText="Title is required." />);
    const input = screen.getByLabelText('Event title');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAccessibleDescription('Title is required.');
  });
});

describe('SearchInput', () => {
  it('is labeled even when the label is visually hidden', () => {
    render(<SearchInput label="Search events" value="" onChange={() => {}} />);
    expect(screen.getByLabelText('Search events')).toBeInTheDocument();
  });

  it('shows a clear button only when there is a value, and calls onClear', async () => {
    const onClear = vi.fn();
    const { rerender } = render(<SearchInput label="Search events" value="" onChange={() => {}} onClear={onClear} />);
    expect(screen.queryByRole('button', { name: 'Clear search' })).not.toBeInTheDocument();

    rerender(<SearchInput label="Search events" value="vehicle" onChange={() => {}} onClear={onClear} />);
    await userEvent.click(screen.getByRole('button', { name: 'Clear search' }));
    expect(onClear).toHaveBeenCalledOnce();
  });
});

describe('Select', () => {
  it('is a native select with every option present', () => {
    render(
      <Select
        label="Status"
        value="open"
        onChange={() => {}}
        options={[
          { value: 'open', label: 'Open' },
          { value: 'closed', label: 'Closed' },
        ]}
      />,
    );
    const select = screen.getByLabelText('Status') as HTMLSelectElement;
    expect(select.tagName).toBe('SELECT');
    expect(screen.getByRole('option', { name: 'Open' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Closed' })).toBeInTheDocument();
  });
});

function ControlledTabs() {
  const [value, setValue] = useState('a');
  return (
    <>
      <Tabs items={[{ value: 'a', label: 'Tab A' }, { value: 'b', label: 'Tab B' }]} value={value} onChange={setValue} />
      <p>active: {value}</p>
    </>
  );
}

describe('Tabs', () => {
  it('supports arrow-key navigation between tabs (roving tabindex)', async () => {
    render(<ControlledTabs />);
    const tabA = screen.getByRole('tab', { name: 'Tab A' });
    tabA.focus();
    expect(screen.getByText('active: a')).toBeInTheDocument();

    await userEvent.keyboard('{ArrowRight}');
    expect(screen.getByText('active: b')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Tab B' })).toHaveFocus();
  });

  it('marks the selected tab with aria-selected', () => {
    render(<ControlledTabs />);
    expect(screen.getByRole('tab', { name: 'Tab A' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Tab B' })).toHaveAttribute('aria-selected', 'false');
  });
});
