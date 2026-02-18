import { DefineComponent } from 'vue';

export interface KnowledgeChatContext {
  topic?: string;
  keywords?: string[];
  file_count?: number;
}

declare const KnowledgePersistenceDialog: DefineComponent<
  {
    visible: { type: BooleanConstructor; default: false };
    chatId: { type: StringConstructor; required: false; default: null };
    chatContext: { type: ObjectConstructor; default: null };
  },
  {},
  any
>;
export default KnowledgePersistenceDialog;
