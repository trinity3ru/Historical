
import React from 'react';

const WelcomeMessage: React.FC = () => {
  return (
    <div className="text-center p-8 bg-slate-800/50 rounded-lg">
      <h2 className="text-2xl font-bold text-slate-100 mb-2">Welcome to the Historical Object Finder</h2>
      <p className="text-slate-400">
        Upload a photo of an object, and I'll analyze it to see if it's a historical artifact.
      </p>
      <p className="text-slate-400 mt-2">
        Use the button below to get started!
      </p>
    </div>
  );
};

export default WelcomeMessage;
