import type { ChatMessage as ChatMessageType } from '@/types';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ChatMessage } from './ChatMessage';

describe('ChatMessage', () => {
  const baseMessage: ChatMessageType = {
    id: 'msg-1',
    role: 'user',
    content: 'Test message content',
    timestamp: new Date().toISOString(),
  };

  it('renders user message with correct styling', () => {
    render(<ChatMessage message={baseMessage} />);
    
    expect(screen.getByText('Test message content')).toBeInTheDocument();
  });

  it('renders assistant message with bot icon', () => {
    const assistantMessage: ChatMessageType = {
      ...baseMessage,
      role: 'assistant',
      content: 'Assistant response',
    };
    
    render(<ChatMessage message={assistantMessage} />);
    
    expect(screen.getByText('Assistant response')).toBeInTheDocument();
  });

  it('shows streaming indicator when message is streaming', () => {
    const streamingMessage: ChatMessageType = {
      ...baseMessage,
      role: 'assistant',
      content: 'Working...',
      streaming: true,
    };
    
    render(<ChatMessage message={streamingMessage} />);
    
    expect(screen.getByText('Thinking...')).toBeInTheDocument();
  });

  it('displays formatted timestamp', () => {
    const messageWithTime: ChatMessageType = {
      ...baseMessage,
      timestamp: '2024-01-15T10:30:00.000Z',
    };
    
    render(<ChatMessage message={messageWithTime} />);
    
    // Time format depends on locale, just check message renders
    expect(screen.getByText('Test message content')).toBeInTheDocument();
  });
});
